"""
Simple JSON state persistence so a paper/live runner can be invoked
repeatedly (manually or on a schedule) and remember its balance/open
position between runs, instead of resetting every time.
"""

import json
import os


def load_state(state_file: str, starting_balance: float) -> dict:
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {"balance": starting_balance, "position": None}


def save_state(state_file: str, balance: float, position):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump({"balance": balance, "position": position}, f, indent=2)
