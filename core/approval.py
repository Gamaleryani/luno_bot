"""
File-based approval gate for big LIVE trades only (paper/backtest never
risk real money, so they just notify - see core/notifier.py - and never
block).

Two ways a pending trade executes:
1. You explicitly approve it (approve_trade.py) - executes on the next check.
2. You DON'T respond within APPROVAL_TIMEOUT_SECONDS (see config.py) - the
   bot re-checks that the trade still makes sense (price hasn't moved past
   tolerance) and executes anyway. This is a deliberate fail-OPEN design,
   not fail-closed - chosen because a human might be asleep/working/away
   and an indefinite hold could mean missing a real signal. Weigh that
   tradeoff before setting a short timeout: 5 minutes is barely enough time
   to notice a phone notification, let alone evaluate a trade. A stale
   proposal (price moved beyond tolerance) is never executed either way -
   it's dropped and a fresh one queued.
"""

import json
import os
import time


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, "pending_trade.json")


def get_pending(state_dir: str):
    p = _path(state_dir)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def queue_pending(state_dir: str, trade: dict):
    os.makedirs(state_dir, exist_ok=True)
    trade = dict(trade)
    trade["approved"] = False
    trade["queued_at"] = time.time()
    with open(_path(state_dir), "w") as f:
        json.dump(trade, f, indent=2)


def approve(state_dir: str) -> bool:
    p = _path(state_dir)
    if not os.path.exists(p):
        return False
    with open(p) as f:
        trade = json.load(f)
    trade["approved"] = True
    with open(p, "w") as f:
        json.dump(trade, f, indent=2)
    return True


def clear_pending(state_dir: str):
    p = _path(state_dir)
    if os.path.exists(p):
        os.remove(p)


def is_stale(pending, action: str, price: float, tolerance_pct: float = 0.01) -> bool:
    """True if this pending trade no longer matches what's being proposed
    now (wrong action, or price moved beyond tolerance) - a stale proposal
    is never executed, approved or not."""
    if not pending or pending.get("action") != action:
        return True
    ref_price = pending.get("price", 0)
    if ref_price <= 0:
        return True
    return abs(price - ref_price) / ref_price > tolerance_pct


def is_expired(pending, timeout_seconds: float) -> bool:
    queued_at = pending.get("queued_at") if pending else None
    if not queued_at:
        return False
    return (time.time() - queued_at) >= timeout_seconds


def should_execute(pending, action: str, price: float, timeout_seconds: float,
                    tolerance_pct: float = 0.01) -> bool:
    """Executes if the trade is still valid (not stale) AND either
    explicitly approved or the timeout has elapsed (fail-open)."""
    if is_stale(pending, action, price, tolerance_pct):
        return False
    return pending.get("approved") is True or is_expired(pending, timeout_seconds)
