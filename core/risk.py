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
                entry_timestamp: float = None, current_timestamp: float = None,
                peak_price: float = None, current_adx: float = None) -> dict:
    """Check whether an open position should be closed on stop-loss,
    take-profit, a trailing stop, or (if cfg.MAX_HOLD_HOURS is set AND both
    timestamps are given) a max holding time - all opt-in beyond stop-loss,
    unused by default so existing profiles are unaffected.

    cfg.TRAILING_STOP_PCT (opt-in, requires peak_price) replaces the fixed
    TAKE_PROFIT_PCT with a ratcheting exit: instead of always selling at a
    fixed gain, it rides the position as long as price keeps making new
    highs and only exits once price falls this % back from the highest
    point seen - built to let a real trend run instead of capping winners
    the moment TAKE_PROFIT_PCT is first touched.

    cfg.STRONG_TREND_ADX_THRESHOLD (opt-in, requires current_adx) widens
    both the stop-loss and the trailing stop to cfg.STRONG_TREND_STOP_LOSS_PCT
    / cfg.STRONG_TREND_TRAILING_STOP_PCT whenever ADX is at or above that
    threshold - a confirmed strong trend gets more room to breathe instead
    of being shaken out by normal volatility on the way to its real reversal."""
    strong_adx_threshold = getattr(cfg, "STRONG_TREND_ADX_THRESHOLD", None)
    in_strong_trend = (strong_adx_threshold is not None and current_adx is not None
                        and current_adx >= strong_adx_threshold)

    stop_loss_pct = cfg.STOP_LOSS_PCT
    if in_strong_trend:
        stop_loss_pct = getattr(cfg, "STRONG_TREND_STOP_LOSS_PCT", stop_loss_pct)

    change_pct = (current_price - entry_price) / entry_price
    if change_pct <= -stop_loss_pct:
        return {"exit": True, "reason": f"stop-loss hit: {change_pct*100:.1f}%"}

    trailing_pct = getattr(cfg, "TRAILING_STOP_PCT", None)
    if in_strong_trend:
        trailing_pct = getattr(cfg, "STRONG_TREND_TRAILING_STOP_PCT", trailing_pct)

    if trailing_pct and peak_price is not None:
        peak = max(peak_price, current_price)
        drawdown_from_peak = (peak - current_price) / peak
        if drawdown_from_peak >= trailing_pct:
            return {"exit": True, "reason": f"trailing stop hit: fell {drawdown_from_peak*100:.1f}% "
                                             f"from peak {peak:.2f} ({change_pct*100:+.1f}% overall)"
                                             + (" [strong-trend override]" if in_strong_trend else "")}
    elif change_pct >= cfg.TAKE_PROFIT_PCT:
        return {"exit": True, "reason": f"take-profit hit: {change_pct*100:.1f}%"}

    max_hold_hours = getattr(cfg, "MAX_HOLD_HOURS", None)
    if max_hold_hours and entry_timestamp is not None and current_timestamp is not None:
        held_hours = (current_timestamp - entry_timestamp) / 3600
        if held_hours >= max_hold_hours:
            return {"exit": True, "reason": f"max hold time reached: {held_hours:.1f}h "
                                             f"({change_pct*100:+.1f}%)"}

    return {"exit": False, "reason": None}
