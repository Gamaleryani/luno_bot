"""
Per-strategy capital allocation - how much each profile is allowed to
trade with, independent of both the other profile and whatever the real
Luno wallet actually holds.

Edit allocations.json directly (e.g. via GitHub's web file editor - no
code, no token needed, just log into your own repo and change the number)
to change how much a strategy trades with. This is deliberately NOT a form
on the public dashboard: the dashboard is static and public, so any control
that could change trading behavior would need write credentials embedded in
page JS that anyone visiting the site could read - a real security hole.
Editing the file directly is the safe equivalent.

In live mode, this is a soft cap only - core.luno_client.get_balances() is
still checked before every real trade to make sure the money is actually
there (see main.py's balance-check safeguard). Changing this number does
NOT move real money or resize an already-open position; it only affects
the size of the NEXT new trade.
"""

import json
import os

ALLOCATIONS_FILE = "allocations.json"


def load_allocation(profile_name: str, fallback: float) -> float:
    if not os.path.exists(ALLOCATIONS_FILE):
        return fallback
    try:
        with open(ALLOCATIONS_FILE) as f:
            data = json.load(f)
        return float(data.get(profile_name, fallback))
    except (ValueError, TypeError, json.JSONDecodeError):
        print(f"[allocations] couldn't read {ALLOCATIONS_FILE}, using fallback {fallback}")
        return fallback
