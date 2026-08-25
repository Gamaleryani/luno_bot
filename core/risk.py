"""
Risk controls. This module never lets the strategy override safety rules -
stop-loss/take-profit checks always run before any new decision is acted on.
"""


def position_size(balance: float, atr: float, price: float, cfg) -> float:
    """
    Volatility-adaptive sizing: higher ATR (volatility) relative to price
    shrinks the position size. Returns amount in quote currency (e.g. MYR) to risk.
    """
    if price <= 0 or atr != atr or atr <= 0:
        return balance * cfg.VOLATILITY_SIZE_FLOOR

    volatility_pct = atr / price
    # scale: more volatility -> smaller fraction of MAX_POSITION_PCT used
    scale = max(cfg.VOLATILITY_SIZE_FLOOR, 1 - min(volatility_pct * 10, 0.85))
    size = balance * cfg.MAX_POSITION_PCT * scale
    return round(size, 2)


def check_exit(entry_price: float, current_price: float, cfg,
                entry_timestamp: float = None, current_timestamp: float = None) -> dict:
    """Check whether an open position should be closed on stop-loss,
    take-profit, or (if cfg.MAX_HOLD_HOURS is set AND both timestamps are
    given) a max holding time - the latter is what makes a "day trading"
    style profile actually day-trading rather than just tight stops; it's
    opt-in and unused by default so existing profiles are unaffected."""
    change_pct = (current_price - entry_price) / entry_price
    if change_pct <= -cfg.STOP_LOSS_PCT:
        return {"exit": True, "reason": f"stop-loss hit: {change_pct*100:.1f}%"}
    if change_pct >= cfg.TAKE_PROFIT_PCT:
        return {"exit": True, "reason": f"take-profit hit: {change_pct*100:.1f}%"}

    max_hold_hours = getattr(cfg, "MAX_HOLD_HOURS", None)
    if max_hold_hours and entry_timestamp is not None and current_timestamp is not None:
        held_hours = (current_timestamp - entry_timestamp) / 3600
        if held_hours >= max_hold_hours:
            return {"exit": True, "reason": f"max hold time reached: {held_hours:.1f}h "
                                             f"({change_pct*100:+.1f}%)"}

    return {"exit": False, "reason": None}
