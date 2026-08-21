"""
Live/paper runner. Polls Luno for recent candles, runs the strategy, and
executes trades according to config.MODE ("paper" simulates, "live"
places real orders - see core/luno_client.py for the gate).

Supports named profiles (core/profiles.py) so multiple strategies can run
in parallel against the same account, each with its own persisted state
(state/<profile>.json) and log directory (logs/<profile>/).

Every trade sends an email notification (see core/notifier.py - requires
EMAIL_* env vars, no-ops with a warning if unset). In MODE="live", a trade
at or above BIG_TRADE_ALERT_PCT of balance is NOT executed immediately -
it's queued and emailed for approval instead (see core/approval.py,
approve_trade.py). Paper/backtest never risk real money, so they just
notify and execute immediately.

This does NOT run automatically on a schedule - run it manually or wire
it to a cron/Task Scheduler entry once you've reviewed paper results.

Usage:
    python main.py --profile trend_4h
    python main.py --profile range_1h_defensive
"""

import argparse
import time

import pandas as pd

import config as cfg
from core import indicators, strategy, risk, logger, state as state_mod, notifier, approval
from core.luno_client import LunoClient
from core.profiles import apply_profile, PROFILES


def fetch_recent_df(client: LunoClient) -> pd.DataFrame:
    since_ms = int((time.time() - cfg.CANDLE_DURATION * 500) * 1000)
    candles = client.get_candles(cfg.PAIR, cfg.CANDLE_DURATION, since_ms)
    df = pd.DataFrame(candles)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


def is_big_trade(size_myr: float, balance: float) -> bool:
    threshold_pct = getattr(cfg, "BIG_TRADE_ALERT_PCT", 0.30)
    return balance > 0 and size_myr >= balance * threshold_pct


def _buy(client, profile_name, profile_label, log_dir, approval_dir, balance, size_myr, price, reason, regime):
    big = is_big_trade(size_myr, balance)

    if cfg.MODE == "live" and big:
        pending = approval.get_pending(approval_dir)
        if approval.matches(pending, "BUY", price):
            approval.clear_pending(approval_dir)
            # fall through and execute below
        else:
            approval.queue_pending(approval_dir, {"action": "BUY", "price": price,
                                                    "size_myr": size_myr, "reason": reason})
            notifier.notify(
                f"[APPROVAL NEEDED] {profile_label}: BUY @ {price:.2f}",
                f"Proposed BUY of {size_myr:.2f} MYR @ {price:.2f}.\nReason: {reason}\n\n"
                f"Run `python approve_trade.py {profile_name}` to approve. Nothing will "
                f"execute until you do, and this expires if the bot's decision changes.",
            )
            print(f"BUY of {size_myr:.2f} MYR is above the approval threshold - "
                  f"queued for approval, not executed.")
            return balance, None

    size_units = size_myr / price
    client.place_order(cfg.PAIR, "BID", size_units, price)
    position = {"entry_price": price, "size_myr": size_myr, "size_units": size_units,
                "entry_timestamp": time.time()}
    balance -= size_myr
    logger.log_event(log_dir, {"action": "BUY", "price": price, "balance": balance,
                                "regime": regime, "reason": reason})
    notifier.trade_notification(profile_label, "BUY", price, size_myr, balance, reason, big)
    return balance, position


def _sell(client, profile_name, profile_label, log_dir, approval_dir, balance, position, price, reason, regime):
    size_myr = position["size_myr"]
    big = is_big_trade(size_myr, balance + size_myr)

    if cfg.MODE == "live" and big:
        pending = approval.get_pending(approval_dir)
        if not approval.matches(pending, "SELL", price):
            approval.queue_pending(approval_dir, {"action": "SELL", "price": price,
                                                    "size_myr": size_myr, "reason": reason})
            notifier.notify(
                f"[APPROVAL NEEDED] {profile_label}: SELL @ {price:.2f}",
                f"Proposed SELL of {size_myr:.2f} MYR position @ {price:.2f}.\nReason: {reason}\n\n"
                f"Run `python approve_trade.py {profile_name}` to approve. Nothing will "
                f"execute until you do, and this expires if the bot's decision changes.",
            )
            print("SELL is above the approval threshold - queued for approval, not executed.")
            return balance, position  # keep holding until approved
        approval.clear_pending(approval_dir)

    client.place_order(cfg.PAIR, "ASK", position["size_units"], price)
    pnl = (price - position["entry_price"]) * position["size_units"]
    balance += size_myr + pnl
    logger.log_event(log_dir, {"action": "SELL", "price": price, "balance": balance,
                                "regime": regime, "reason": reason})
    notifier.trade_notification(profile_label, "SELL", price, size_myr, balance, reason, big)
    return balance, None


def run_once(client: LunoClient, profile_name: str, profile_label: str,
             log_dir: str, approval_dir: str, balance: float, position):
    df = fetch_recent_df(client)
    df = indicators.compute_all(df, cfg)
    i = len(df) - 1
    row = df.iloc[i]
    price = row["close"]

    # 1. manage any open position first (stop-loss / take-profit)
    if position is not None:
        exit_check = risk.check_exit(position["entry_price"], price, cfg)
        if exit_check["exit"]:
            return _sell(client, profile_name, profile_label, log_dir, approval_dir,
                          balance, position, price, exit_check["reason"], "-")

    # 2. evaluate strategy for a new decision
    decision = strategy.evaluate(df, i, cfg)
    print(f"[{decision['action']}] {decision['reason']}")

    if decision["action"] == "BUY" and position is None:
        size_myr = risk.position_size(balance, row.get("atr", 0), price, cfg)
        if 0 < size_myr <= balance:
            return _buy(client, profile_name, profile_label, log_dir, approval_dir,
                        balance, size_myr, price, decision["reason"], decision["regime"])

    elif decision["action"] == "SELL" and position is not None:
        return _sell(client, profile_name, profile_label, log_dir, approval_dir,
                      balance, position, price, decision["reason"], decision["regime"])

    return balance, position


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=list(PROFILES.keys()))
    args = parser.parse_args()

    paths = apply_profile(cfg, args.profile)
    st = state_mod.load_state(paths["state_file"], cfg.STARTING_BALANCE_MYR)

    print(f"Starting in MODE={cfg.MODE} on pair={cfg.PAIR} profile={args.profile} ({paths['label']})")
    client = LunoClient(cfg)
    balance, position = run_once(client, args.profile, paths["label"], paths["log_dir"],
                                  f"state/{args.profile}", st["balance"], st["position"])
    state_mod.save_state(paths["state_file"], balance, position)
    print(f"Done. Balance={balance:.2f} Position={position}")
