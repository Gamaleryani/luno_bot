"""
Approves or rejects a pending big trade for a live-mode profile. In
MODE="live", the bot never executes a trade at or above BIG_TRADE_ALERT_PCT
of balance without a response - it emails/pushes you and waits up to
APPROVAL_TIMEOUT_SECONDS, executing automatically if you don't respond
(fail-open by design - see core/approval.py). This script gives you an
explicit third option: reject it outright before the timeout, rather than
only "approve now" or "do nothing".

Meant to be run via .github/workflows/respond_approval.yml's
workflow_dispatch form (the "Respond to Approval" link on the dashboard) -
works from a phone via the GitHub app, no terminal needed.

Usage:
    python approve_trade.py trend_4h approve
    python approve_trade.py trend_4h reject
"""

import sys

from core import approval
from core.profiles import PROFILES

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in PROFILES or sys.argv[2] not in ("approve", "reject"):
        print(f"Usage: python approve_trade.py <profile> <approve|reject>  (profiles: {list(PROFILES)})")
        sys.exit(1)

    profile, decision = sys.argv[1], sys.argv[2]
    state_dir = f"state/{profile}"
    pending = approval.get_pending(state_dir)
    if pending is None:
        print("No pending trade to respond to.")
        sys.exit(0)

    if decision == "reject":
        approval.clear_pending(state_dir)
        print(f"Rejected: {pending['action']} @ {pending.get('price')} "
              f"({pending.get('size_myr', 0):.2f} MYR). This will NOT execute.")
    else:
        approval.approve(state_dir)
        print(f"Approved: {pending['action']} @ {pending.get('price')} "
              f"({pending.get('size_myr', 0):.2f} MYR).")
        print("It will execute the next time the bot runs, only if the price "
              "hasn't moved much and the bot still wants to make this exact trade.")
