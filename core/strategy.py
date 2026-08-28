"""
The decision engine. Each indicator casts a vote: 1 (bullish/buy),
-1 (bearish/sell), or 0 (neutral). Votes are combined differently
depending on market regime (trending vs ranging) - this is the
"market regime detection" edge described to the user.

A trade only fires when enough votes agree (cfg.MIN_AGREEING_SIGNALS).
Every decision returns its full reasoning so it can be logged.
"""

from .regime import detect_regime


def _rsi_vote(row, cfg, regime):
    rsi = row.get("rsi")
    if rsi != rsi:
        return 0, "rsi: no data"
    if regime == "ranging":
        # mean-reversion logic: fade extremes
        if rsi <= cfg.RSI_OVERSOLD:
            return 1, f"rsi {rsi:.1f} oversold (ranging regime -> buy)"
        if rsi >= cfg.RSI_OVERBOUGHT:
            return -1, f"rsi {rsi:.1f} overbought (ranging regime -> sell)"
    else:
        # trending logic: RSI confirms momentum direction instead of fading it
        if rsi >= 55:
            return 1, f"rsi {rsi:.1f} confirms upward momentum (trending)"
        if rsi <= 45:
            return -1, f"rsi {rsi:.1f} confirms downward momentum (trending)"
    return 0, f"rsi {rsi:.1f} neutral"


def _ma_vote(row, prev_row, cfg):
    fast, slow = row.get("ma_fast"), row.get("ma_slow")
    pfast, pslow = prev_row.get("ma_fast"), prev_row.get("ma_slow")
    if any(v != v for v in [fast, slow, pfast, pslow]):
        return 0, "ma: no data"
    crossed_up = pfast <= pslow and fast > slow
    crossed_down = pfast >= pslow and fast < slow
    if crossed_up:
        return 1, "fast MA crossed above slow MA (bullish crossover)"
    if crossed_down:
        return -1, "fast MA crossed below slow MA (bearish crossover)"
    if fast > slow:
        return 1, "fast MA above slow MA (uptrend intact)"
    if fast < slow:
        return -1, "fast MA below slow MA (downtrend intact)"
    return 0, "ma: flat"


def _bollinger_vote(row, cfg):
    close, lower, upper = row.get("close"), row.get("bb_lower"), row.get("bb_upper")
    if any(v != v for v in [close, lower, upper]):
        return 0, "no data"
    if close <= lower:
        return 1, "price at/below lower Bollinger Band (oversold)"
    if close >= upper:
        return -1, "price at/above upper Bollinger Band (overbought)"
    return 0, "mid-range, no extreme"


def _volume_vote(row, direction_hint, cfg):
    ratio = row.get("volume_ratio")
    if ratio != ratio:
        return 0, "volume: no data"
    if ratio >= 1.5 and direction_hint > 0:
        return 1, f"volume {ratio:.1f}x average confirms bullish move"
    if ratio >= 1.5 and direction_hint < 0:
        return -1, f"volume {ratio:.1f}x average confirms bearish move"
    if ratio < 0.7:
        return 0, f"volume {ratio:.1f}x average is weak - low confidence"
    return 0, "volume: neutral"


def evaluate(df, idx, cfg):
    """
    Evaluate the strategy at row `idx` of the indicator-enriched DataFrame.
    Returns a dict with the decision and full reasoning trail.
    """
    row = df.iloc[idx]
    prev_row = df.iloc[idx - 1] if idx > 0 else row

    regime = detect_regime(row, cfg)

    # news-shock filter: pause if this candle moved too violently
    price_change = abs(row["close"] - prev_row["close"]) / prev_row["close"] if prev_row["close"] else 0
    if price_change >= cfg.NEWS_SHOCK_PCT:
        return {
            "action": "HOLD",
            "regime": regime,
            "reason": f"news-shock filter triggered: {price_change*100:.1f}% single-candle move, sitting out",
            "votes": {},
        }

    allowed_regimes = getattr(cfg, "ALLOWED_REGIMES", None)
    if allowed_regimes is not None and regime not in allowed_regimes:
        return {
            "action": "HOLD",
            "regime": regime,
            "reason": f"regime '{regime}' not in ALLOWED_REGIMES {allowed_regimes} - sitting out",
            "votes": {},
        }

    rsi_v, rsi_r = _rsi_vote(row, cfg, regime)
    ma_v, ma_r = _ma_vote(row, prev_row, cfg)
    bb_v, bb_r = _bollinger_vote(row, cfg)
    direction_hint = rsi_v + ma_v + bb_v
    vol_v, vol_r = _volume_vote(row, direction_hint, cfg)

    votes = {"rsi": rsi_v, "ma": ma_v, "bollinger": bb_v, "volume": vol_v}
    reasons = {"rsi": rsi_r, "ma": ma_r, "bollinger": bb_r, "volume": vol_r}

    bullish = sum(1 for v in votes.values() if v == 1)
    bearish = sum(1 for v in votes.values() if v == -1)

    if bullish >= cfg.MIN_AGREEING_SIGNALS:
        action = "BUY"
    elif bearish >= cfg.MIN_AGREEING_SIGNALS:
        action = "SELL"
    else:
        action = "HOLD"

    return {
        "action": action,
        "regime": regime,
        "reason": f"{bullish} bullish / {bearish} bearish votes (need {cfg.MIN_AGREEING_SIGNALS}) in {regime} regime",
        "votes": votes,
        "vote_reasons": reasons,
    }
