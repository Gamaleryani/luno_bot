"""
Manual command interface - lets you query market state or issue a BUY/SELL
for a profile that gets checked against the same risk rules as the
automated bot, then executed and logged like any other trade (tagged
MANUAL in the reason column so it's distinguishable in the log/dashboard).

This is meant to be run via .github/workflows/manual_command.yml's
workflow_dispatch form (a text field on GitHub's own Actions UI - see the
"Manual Command" link on the dashboard), not typed into the public
dashboard itself: a text box that can execute trades can't safely live on
a public static page (see core/allocations.py's docstring for the same
reasoning applied to allocation editing).

A manual command never goes through the big-trade approval queue
(core/approval.py) - typing an authenticated command via your own GitHub
login already IS the approval; queueing it for your own later approval
would be circular. Big manual trades still get flagged "[BIG TRADE]" in
their notification for awareness, they just aren't held.

Commands:
    QUERY <profile>
    BUY <profile> <amount_myr>   - opens a new position, or ADDS to an
                                   existing one if already holding (the
                                   entry price becomes the size-weighted
                                   average of both buys, so stop-loss/
                                   take-profit apply against that average)
    SELL <profile>                - closes the entire position, however it
                                     was built up (one buy or several)

Usage:
    python manual_command.py "QUERY trend_4h"
    python manual_command.py "BUY trend_4h 20"
    python manual_command.py "SELL trend_4h"
"""

import sys
import time

import config as cfg
from core import indicators, strategy, risk, logger, state as state_mod, notifier, allocations
from core.luno_client import LunoClient
from core.profiles import apply_profile, PROFILES
from main import fetch_recent_df, is_big_trade, check_real_balance


def run_query(client, profile_name, profile_label, balance, position, allocation):
    df = fetch_recent_df(client)
    df = indicators.compute_all(df, cfg)
    row = df.iloc[-1]
    decision = strategy.evaluate(df, len(df) - 1, cfg)
    print(f"--- {profile_label} ---")
    print(f"Price: {row['close']:.2f} MYR")
    print(f"Regime: {decision['regime']}")
    print(f"What the bot would decide right now: {decision['action']} ({decision['reason']})")
    print(f"Balance: {balance:.2f} MYR (allocated: {allocation:.2f} MYR)")
    if position:
        print(f"Position: {position['size_units']:.8f} XBT @ {position['entry_price']:.2f} "
              f"({position['size_myr']:.2f} MYR)")
    else:
        print("Position: none (flat)")


def run_buy(client, profile_name, profile_label, log_dir, balance, position, amount_myr, price):
    adding_to_position = position is not None

    if amount_myr <= 0:
        print("REFUSED: amount must be positive.")
        return balance, position
    if amount_myr > balance:
        print(f"REFUSED: {amount_myr:.2f} MYR exceeds available balance ({balance:.2f} MYR).")
        return balance, position
    max_allowed = balance * cfg.MAX_POSITION_PCT
    if amount_myr > max_allowed:
        print(f"REFUSED: {amount_myr:.2f} MYR exceeds this profile's max position size "
              f"({cfg.MAX_POSITION_PCT*100:.0f}% of balance = {max_allowed:.2f} MYR). "
              f"Resubmit with an amount at or below that, or adjust MAX_POSITION_PCT in config.py.")
        return balance, position

    if cfg.MODE == "live":
        amount_myr = check_real_balance(client, amount_myr)
        if amount_myr <= 0:
            print("Real balance check left nothing to trade with - refusing.")
            return balance, position

    size_units = amount_myr / price
    client.place_order(cfg.PAIR, "BID", size_units, price)
    new_balance = balance - amount_myr

    if adding_to_position:
        total_units = position["size_units"] + size_units
        total_myr = position["size_myr"] + amount_myr
        new_position = {
            "entry_price": total_myr / total_units,  # weighted-average cost basis -
            "size_myr": total_myr,                    # stop-loss/take-profit now apply
            "size_units": total_units,                 # against this average, not the
            "entry_timestamp": position["entry_timestamp"],  # original entry alone
        }
        reason = "MANUAL: user-issued BUY command (added to existing position)"
        print(f"ADDED {size_units:.8f} XBT @ {price:.2f} ({amount_myr:.2f} MYR) to existing position. "
              f"New average entry: {new_position['entry_price']:.2f}, "
              f"total held: {total_units:.8f} XBT ({total_myr:.2f} MYR). "
              f"New balance: {new_balance:.2f} MYR.")
    else:
        new_position = {"entry_price": price, "size_myr": amount_myr, "size_units": size_units,
                         "entry_timestamp": time.time()}
        reason = "MANUAL: user-issued BUY command"
        print(f"BOUGHT {size_units:.8f} XBT @ {price:.2f} ({amount_myr:.2f} MYR). "
              f"New balance: {new_balance:.2f} MYR.")

    logger.log_event(log_dir, {"action": "BUY", "price": price, "balance": new_balance,
                                "regime": "-", "reason": reason})
    notifier.trade_notification(profile_label, "BUY", price, amount_myr, new_balance, reason,
                                 is_big_trade(amount_myr, balance))
    return new_balance, new_position


def run_sell(client, profile_label, log_dir, balance, position, price):
    if position is None:
        print(f"REFUSED: {profile_label} has no open position to sell.")
        return balance, position

    size_myr = position["size_myr"]
    client.place_order(cfg.PAIR, "ASK", position["size_units"], price)
    pnl = (price - position["entry_price"]) * position["size_units"]
    new_balance = balance + size_myr + pnl
    reason = "MANUAL: user-issued SELL command"
    logger.log_event(log_dir, {"action": "SELL", "price": price, "balance": new_balance,
                                "regime": "-", "reason": reason})
    notifier.trade_notification(profile_label, "SELL", price, size_myr, new_balance, reason,
                                 is_big_trade(size_myr, balance))
    print(f"SOLD @ {price:.2f}. P/L: {pnl:+.2f} MYR. New balance: {new_balance:.2f} MYR.")
    return new_balance, None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python manual_command.py "QUERY|BUY|SELL <profile> [amount]"')
        sys.exit(1)

    parts = sys.argv[1].strip().split()
    if len(parts) < 2:
        print("Command must be at least: ACTION profile")
        sys.exit(1)

    action, profile_name = parts[0].upper(), parts[1]
    if profile_name not in PROFILES:
        print(f"Unknown profile '{profile_name}'. Choices: {list(PROFILES)}")
        sys.exit(1)

    paths = apply_profile(cfg, profile_name)
    allocation = allocations.load_allocation(profile_name, cfg.STARTING_BALANCE_MYR)
    st = state_mod.load_state(paths["state_file"], allocation)
    balance, position = st["balance"], st["position"]

    client = LunoClient(cfg)
    df = fetch_recent_df(client)
    df = indicators.compute_all(df, cfg)
    price = df.iloc[-1]["close"]

    if action == "QUERY":
        run_query(client, profile_name, paths["label"], balance, position, allocation)
    elif action == "BUY":
        if len(parts) != 3:
            print("Usage: BUY <profile> <amount_myr>")
            sys.exit(1)
        amount = float(parts[2])
        balance, position = run_buy(client, profile_name, paths["label"], paths["log_dir"],
                                     balance, position, amount, price)
        state_mod.save_state(paths["state_file"], balance, position)
    elif action == "SELL":
        balance, position = run_sell(client, paths["label"], paths["log_dir"], balance, position, price)
        state_mod.save_state(paths["state_file"], balance, position)
    else:
        print(f"Unknown action '{action}'. Use QUERY, BUY, or SELL.")
        sys.exit(1)
