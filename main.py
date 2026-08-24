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
from core import indicators, strategy, risk, logger, state as state_mod, notifier, approval, allocations
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


def check_real_balance(client, size_myr: float) -> float:
    """Live-mode safeguard: verifies real MYR actually available on Luno
    before trusting the bot's internal tracked balance. Returns the size to
    actually use (capped to what's really free), which may be 0 if there's
    not enough. Never raises - a failed balance check should block the
    trade, not crash the run."""
    try:
        balances = client.get_balances()
        real_myr = float(balances.get("MYR", {}).get("balance", 0))
    except Exception as e:
        print(f"[balance-check] failed to fetch real balance: {e} - refusing to trade this round.")
        return 0.0
    if real_myr < size_myr:
        print(f"[balance-check] internal tracker wanted to spend {size_myr:.2f} MYR but Luno "
              f"only shows {real_myr:.2f} MYR free - capping to what's actually available.")
        notifier.notify(
            "[BALANCE MISMATCH] luno_bot",
            f"Wanted to spend {size_myr:.2f} MYR but Luno's real balance is only {real_myr:.2f} MYR. "
            f"Trade size capped accordingly. This means the bot's internal tracker has drifted from "
            f"reality - worth checking why (manual trade/withdrawal on this account?).",
            urgent=True,
        )
    return min(size_myr, real_myr)


def _buy(client, profile_name, profile_label, log_dir, approval_dir, balance, size_myr, price, reason, regime):
    big = is_big_trade(size_myr, balance)

    if cfg.MODE == "live" and big:
        pending = approval.get_pending(approval_dir)
        timeout = getattr(cfg, "APPROVAL_TIMEOUT_SECONDS", 300)
        if approval.should_execute(pending, "BUY", price, timeout):
            auto = pending.get("approved") is not True
            approval.clear_pending(approval_dir)
            if auto:
                print("Approval window elapsed with no response - proceeding (fail-open, "
                      "trade still checks out).")
            # fall through and execute below
        elif pending and not approval.is_stale(pending, "BUY", price):
            # already queued and still valid - leave it alone. Re-queuing here
            # would reset queued_at and the 5-minute window would never elapse.
            print("Still waiting on approval or timeout for an existing pending BUY.")
            return balance, None
        else:
            approval.queue_pending(approval_dir, {"action": "BUY", "price": price,
                                                    "size_myr": size_myr, "reason": reason})
            notifier.notify(
                f"[APPROVAL NEEDED] {profile_label}: BUY @ {price:.2f}",
                f"Proposed BUY of {size_myr:.2f} MYR @ {price:.2f}.\nReason: {reason}\n\n"
                f"Run `python approve_trade.py {profile_name}` to approve now, or do nothing - "
                f"it executes automatically after {timeout // 60:.0f} min if the trade still "
                f"checks out. It's dropped instead if the price moves too much in the meantime.",
                urgent=True,
            )
            print(f"BUY of {size_myr:.2f} MYR is above the approval threshold - "
                  f"queued for approval (auto-executes in {timeout}s if no response).")
            return balance, None

    if cfg.MODE == "live":
        size_myr = check_real_balance(client, size_myr)
        if size_myr <= 0:
            print("Real balance check left nothing to trade with - skipping this buy.")
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
        timeout = getattr(cfg, "APPROVAL_TIMEOUT_SECONDS", 300)
        if approval.should_execute(pending, "SELL", price, timeout):
            if pending.get("approved") is not True:
                print("Approval window elapsed with no response - proceeding (fail-open, "
                      "trade still checks out).")
            approval.clear_pending(approval_dir)
            # fall through and execute below
        elif pending and not approval.is_stale(pending, "SELL", price):
            # already queued and still valid - leave it alone. Re-queuing here
            # would reset queued_at and the 5-minute window would never elapse.
            print("Still waiting on approval or timeout for an existing pending SELL.")
            return balance, position
        else:
            approval.queue_pending(approval_dir, {"action": "SELL", "price": price,
                                                    "size_myr": size_myr, "reason": reason})
            notifier.notify(
                f"[APPROVAL NEEDED] {profile_label}: SELL @ {price:.2f}",
                f"Proposed SELL of {size_myr:.2f} MYR position @ {price:.2f}.\nReason: {reason}\n\n"
                f"Run `python approve_trade.py {profile_name}` to approve now, or do nothing - "
                f"it executes automatically after {timeout // 60:.0f} min if the trade still "
                f"checks out.",
                urgent=True,
            )
            print(f"SELL is above the approval threshold - queued for approval "
                  f"(auto-executes in {timeout}s if no response).")
            return balance, position  # keep holding until approved or timed out

    client.place_order(cfg.PAIR, "ASK", position["size_units"], price)
    pnl = (price - position["entry_price"]) * position["size_units"]
    balance += size_myr + pnl
    logger.log_event(log_dir, {"action": "SELL", "price": price, "balance": balance,
                                "regime": regime, "reason": reason})
    notifier.trade_notification(profile_label, "SELL", price, size_myr, balance, reason, big)
    return balance, None


def run_once(client: LunoClient, profile_name: str, profile_label: str,
             log_dir: str, approval_dir: str, balance: float, position,
             manual_hold: bool = False):
    df = fetch_recent_df(client)
    df = indicators.compute_all(df, cfg)
    i = len(df) - 1
    row = df.iloc[i]
    price = row["close"]

    if manual_hold and position is not None:
        # user-set override (manual_command.py HOLD) - skip both the
        # stop-loss/take-profit check and the strategy's own SELL decision
        # entirely. No automatic loss protection while this is on.
        logger.log_price(log_dir, price, "-", balance)
        print(f"[HOLD ACTIVE] skipping automated exit checks for {profile_label} "
              f"- use 'SELL {profile_name}' or 'RESUME {profile_name}' to change this.")
        return balance, position

    # 1. manage any open position first (stop-loss / take-profit)
    if position is not None:
        exit_check = risk.check_exit(position["entry_price"], price, cfg)
        if exit_check["exit"]:
            logger.log_price(log_dir, price, "-", balance)
            return _sell(client, profile_name, profile_label, log_dir, approval_dir,
                          balance, position, price, exit_check["reason"], "-")

    # 2. evaluate strategy for a new decision
    decision = strategy.evaluate(df, i, cfg)
    print(f"[{decision['action']}] {decision['reason']}")
    logger.log_price(log_dir, price, decision["regime"], balance)

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
    allocation = allocations.load_allocation(args.profile, cfg.STARTING_BALANCE_MYR)
    st = state_mod.load_state(paths["state_file"], allocation)

    print(f"Starting in MODE={cfg.MODE} on pair={cfg.PAIR} profile={args.profile} ({paths['label']}), "
          f"allocation={allocation:.2f} MYR" + (", MANUAL HOLD ACTIVE" if st["manual_hold"] else ""))
    client = LunoClient(cfg)
    balance, position = run_once(client, args.profile, paths["label"], paths["log_dir"],
                                  f"state/{args.profile}", st["balance"], st["position"],
                                  st["manual_hold"])
    state_mod.save_state(paths["state_file"], balance, position, st["manual_hold"])
    print(f"Done. Balance={balance:.2f} Position={position}")
