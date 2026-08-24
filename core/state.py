"""
Simple JSON state persistence so a paper/live runner can be invoked
repeatedly (manually or on a schedule) and remember its balance/open
position between runs, instead of resetting every time.

`manual_hold` is a user-set override (see manual_command.py's HOLD/RESUME
commands): while True, the automated bot skips its own stop-loss/
take-profit check AND its own strategy-driven SELL decision for that
profile entirely - only a manual SELL command closes the position. This
means no automatic loss protection while it's on; that trade-off is the
user's explicit choice each time they turn it on, not a default.
"""

import json
import os


def load_state(state_file: str, starting_balance: float) -> dict:
    if os.path.exists(state_file):
        with open(state_file) as f:
            data = json.load(f)
        data.setdefault("manual_hold", False)
        return data
    return {"balance": starting_balance, "position": None, "manual_hold": False}


def save_state(state_file: str, balance: float, position, manual_hold: bool = False):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump({"balance": balance, "position": position, "manual_hold": manual_hold},
                   f, indent=2)
