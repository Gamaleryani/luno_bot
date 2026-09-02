"""
Post-sell dip re-entry: normally, once a position closes, the bot waits for
a completely fresh multi-indicator signal (core/strategy.evaluate) to open a
new one - it has no memory of the trade it just closed. This module adds an
optional second entry path that watches specifically for a dip-and-recovery
after an exit: a defined pullback below the exit price, followed by a simple
reversal confirmation (RSI turning up from oversold, price no longer making
new lows), rather than requiring a full independent signal to form.

Entirely opt-in via cfg.DIP_REENTRY_PCT - unset (the default) means this
never fires, so existing profiles are unaffected. A `dip_watch` dict is
created on every SELL (see backtest.py/main.py) and cleared the moment any
new position opens, however it opened.
"""


def start_dip_watch(exit_price: float, exit_timestamp) -> dict:
    return {"exit_price": exit_price, "exit_timestamp": exit_timestamp,
            "lowest_since_exit": exit_price}


def update_dip_watch(dip_watch: dict, price: float) -> dict:
    """Call once per run while a dip_watch exists and no position is open."""
    dip_watch["lowest_since_exit"] = min(dip_watch.get("lowest_since_exit", dip_watch["exit_price"]), price)
    return dip_watch


def check_dip_reentry(df, idx: int, cfg, dip_watch: dict, current_timestamp) -> dict:
    """Returns {"reentry": bool, "reason": str or None}. Never raises -
    missing indicator data or too little history just means no re-entry yet."""
    dip_pct = getattr(cfg, "DIP_REENTRY_PCT", None)
    if not dip_pct or dip_watch is None:
        return {"reentry": False, "reason": None}

    cooldown_hours = getattr(cfg, "DIP_REENTRY_COOLDOWN_HOURS", 0)
    exit_timestamp = dip_watch.get("exit_timestamp")
    if exit_timestamp is not None and current_timestamp is not None:
        if (current_timestamp - exit_timestamp) / 3600 < cooldown_hours:
            return {"reentry": False, "reason": None}

    exit_price = dip_watch["exit_price"]
    lowest = dip_watch.get("lowest_since_exit", exit_price)
    dip_so_far = (exit_price - lowest) / exit_price
    if dip_so_far < dip_pct:
        return {"reentry": False, "reason": None}

    confirm_n = getattr(cfg, "DIP_REENTRY_CONFIRM_CANDLES", 2)
    if idx < confirm_n:
        return {"reentry": False, "reason": None}

    row = df.iloc[idx]
    rsi = row.get("rsi")
    prev_rsi = df.iloc[idx - 1].get("rsi")
    if rsi != rsi or prev_rsi != prev_rsi:
        return {"reentry": False, "reason": None}

    recent_rsi = df["rsi"].iloc[max(0, idx - confirm_n):idx + 1]
    was_oversold = bool((recent_rsi <= cfg.RSI_OVERSOLD).any())
    rsi_turning_up = rsi > prev_rsi

    recent_lows = df["low"].iloc[idx - confirm_n + 1: idx + 1]
    no_new_lows = bool((recent_lows.diff().dropna() >= 0).all())

    if was_oversold and rsi_turning_up and no_new_lows:
        return {"reentry": True,
                "reason": f"dip_reentry: {dip_so_far*100:.1f}% dip from exit {exit_price:.2f}, "
                          f"RSI {rsi:.1f} turning up from oversold, lows stabilizing"}
    return {"reentry": False, "reason": None}
