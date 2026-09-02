"""
Runs frequently (every 2 min, see .github/workflows/check_approvals.yml) to
enforce the approval timeout precisely. main.py only runs on each profile's
normal trading schedule (hourly/4-hourly) - far too infrequent to notice a
5-minute window has elapsed. This script does ONE thing: for each profile
with a pending big-trade approval, check whether it should now execute
(explicitly approved, or timed out) and do so - it never runs a fresh
strategy evaluation.

Usage:
    python check_pending_approvals.py
"""

import time

import config as cfg
from core import approval, state as state_mod, dip_reentry
from core.luno_client import LunoClient
from core.profiles import apply_profile, PROFILES
from main import _buy, _sell

if __name__ == "__main__":
    for name in PROFILES:
        paths = apply_profile(cfg, name)
        approval_dir = f"state/{name}"
        pending = approval.get_pending(approval_dir)
        if not pending:
            continue
        if cfg.MODE != "live":
            print(f"[{name}] has a pending approval but MODE is not 'live' - ignoring "
                  f"(this shouldn't normally happen).")
            continue

        client = LunoClient(cfg)
        try:
            ticker = client.get_ticker(cfg.PAIR)
            price = float(ticker["last_trade"])
        except Exception as e:
            print(f"[{name}] couldn't fetch price to check pending approval: {e}")
            continue

        timeout = getattr(cfg, "APPROVAL_TIMEOUT_SECONDS", 300)
        if approval.is_stale(pending, pending["action"], price):
            print(f"[{name}] pending {pending['action']} is stale (price moved past "
                  f"tolerance) - dropping without executing.")
            approval.clear_pending(approval_dir)
            continue
        if not approval.should_execute(pending, pending["action"], price, timeout):
            print(f"[{name}] pending {pending['action']} still waiting on approval or timeout.")
            continue

        st = state_mod.load_state(paths["state_file"], cfg.STARTING_BALANCE_MYR)
        balance, position = st["balance"], st["position"]
        manual_hold, dip_watch = st["manual_hold"], st["dip_watch"]

        if pending["action"] == "BUY" and position is None:
            balance, position = _buy(client, name, paths["label"], paths["log_dir"], approval_dir,
                                      balance, pending["size_myr"], price, pending["reason"], "-")
            if position is not None:
                dip_watch = None
        elif pending["action"] == "SELL" and position is not None:
            balance, position = _sell(client, name, paths["label"], paths["log_dir"], approval_dir,
                                       balance, position, price, pending["reason"], "-")
            if position is None:
                dip_watch = dip_reentry.start_dip_watch(price, time.time())
        else:
            print(f"[{name}] pending action no longer matches current position state - "
                  f"dropping stale pending without executing.")
            approval.clear_pending(approval_dir)
            continue

        state_mod.save_state(paths["state_file"], balance, position, manual_hold, dip_watch)
        print(f"[{name}] executed pending {pending['action']} after approval/timeout. "
              f"Balance={balance:.2f} Position={position}")
