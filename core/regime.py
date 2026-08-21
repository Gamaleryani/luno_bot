"""
Decides whether the market is trending or ranging using ADX,
so the strategy can switch its logic accordingly.
"""


def detect_regime(row, cfg) -> str:
    adx = row.get("adx")
    if adx is None or adx != adx:  # NaN check
        return "unknown"
    return "trending" if adx >= cfg.ADX_TREND_THRESHOLD else "ranging"
