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


def check_exit(entry_price: float, current_price: float, cfg) -> dict:
    """Check whether an open position should be closed on stop-loss or take-profit."""
    change_pct = (current_price - entry_price) / entry_price
    if change_pct <= -cfg.STOP_LOSS_PCT:
        return {"exit": True, "reason": f"stop-loss hit: {change_pct*100:.1f}%"}
    if change_pct >= cfg.TAKE_PROFIT_PCT:
        return {"exit": True, "reason": f"take-profit hit: {change_pct*100:.1f}%"}
    return {"exit": False, "reason": None}
