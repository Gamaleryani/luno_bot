"""
File-based approval gate for big LIVE trades only (paper/backtest never
risk real money, so they just notify - see core/notifier.py - and never
block). Default behavior on any doubt is to NOT trade: a big trade
proposal sits pending until you explicitly approve it by running
approve_trade.py, and a stale/unapproved proposal is simply replaced or
dropped rather than ever executing silently.
"""

import json
import os


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


def matches(pending, action: str, price: float, tolerance_pct: float = 0.01) -> bool:
    """An approved pending trade only fires if the bot still wants to make
    almost exactly that trade - if the price moved or the action flipped,
    it's stale and must be re-queued/re-approved, not executed blindly."""
    if not pending or pending.get("action") != action or pending.get("approved") is not True:
        return False
    ref_price = pending.get("price", 0)
    if ref_price <= 0:
        return False
    return abs(price - ref_price) / ref_price <= tolerance_pct
