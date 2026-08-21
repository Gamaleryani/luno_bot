"""
Approves a pending big trade for a live-mode profile. In MODE="live", the
bot never executes a trade at or above BIG_TRADE_ALERT_PCT of balance
without this - it just emails you and queues it, then waits. Nothing
executes until you run this.

Usage:
    python approve_trade.py trend_4h
    python approve_trade.py range_1h_defensive
"""

import sys

from core import approval
from core.profiles import PROFILES

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PROFILES:
        print(f"Usage: python approve_trade.py <profile>  (choices: {list(PROFILES)})")
        sys.exit(1)

    profile = sys.argv[1]
    state_dir = f"state/{profile}"
    pending = approval.get_pending(state_dir)
    if pending is None:
        print("No pending trade to approve.")
        sys.exit(0)

    approval.approve(state_dir)
    print(f"Approved: {pending['action']} @ {pending.get('price')} "
          f"({pending.get('size_myr', 0):.2f} MYR).")
    print("It will execute the next time the bot runs, only if the price "
          "hasn't moved much and the bot still wants to make this exact trade.")
