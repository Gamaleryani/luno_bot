"""
Named strategy profiles, so multiple configurations can run in parallel
against the same account without stepping on each other's logs/state.
Each profile overrides a few attributes on the shared `config` module and
gets its own log directory and state file.

Each profile here was chosen from backtest comparison (see
strategy_compare.py, run against real historical data for that profile's
own PAIR - a strategy validated on Bitcoin does NOT automatically transfer
to another coin) - only configs that consistently beat a buy-and-hold
benchmark across multiple historical windows get added. `PAIR` defaults to
config.py's XBTMYR if a profile doesn't override it.
"""

PROFILES = {
    "trend_4h": {
        "label": "4h wider-stops (trend-friendly)",
        "CANDLE_DURATION": 14400,
        "STOP_LOSS_PCT": 0.05,
        "TAKE_PROFIT_PCT": 0.08,
        # matches .github/workflows/trend_4h.yml's cron: "5 */4 * * *" (UTC)
        "schedule": {"interval_hours": 4, "minute_offset": 5},
    },
    "range_1h_defensive": {
        "label": "1h range-only tight exits (defensive)",
        "CANDLE_DURATION": 3600,
        "ALLOWED_REGIMES": ["ranging"],
        "STOP_LOSS_PCT": 0.02,
        "TAKE_PROFIT_PCT": 0.03,
        # matches .github/workflows/range_1h_defensive.yml's cron: "3 * * * *" (UTC)
        "schedule": {"interval_hours": 1, "minute_offset": 3},
    },
    "eth_range_4h": {
        "label": "ETHMYR 4h range-only (min 2 signals)",
        "PAIR": "ETHMYR",
        "CANDLE_DURATION": 14400,
        "ALLOWED_REGIMES": ["ranging"],
        "MIN_AGREEING_SIGNALS": 2,
        # STOP_LOSS_PCT/TAKE_PROFIT_PCT intentionally left at config.py's
        # defaults (3%/5%) - that's what backtested well, both windows.
        # Validated 2026-08-25 against real ETHMYR history: beat buy-and-hold
        # by +25-55% across a 1-year AND 2-year window (ETH was actually down
        # -17% to -49% over these periods - this range/mean-reversion approach
        # was the only one that stayed profitable in absolute terms, same
        # pattern as range_1h_defensive found for BTC). See strategy_compare.py
        # output in conversation history for full numbers before touching this.
        # matches .github/workflows/eth_range_4h.yml's cron: "20 */4 * * *" (UTC)
        "schedule": {"interval_hours": 4, "minute_offset": 20},
    },
    "sol_range_1h": {
        "label": "SOLMYR 1h range-only tight exits",
        "PAIR": "SOLMYR",
        "CANDLE_DURATION": 3600,
        "ALLOWED_REGIMES": ["ranging"],
        "STOP_LOSS_PCT": 0.02,
        "TAKE_PROFIT_PCT": 0.03,
        # Same structure as range_1h_defensive (BTC) - turns out to transfer.
        # Validated 2026-08-25 against real SOLMYR history: positive in BOTH
        # a 180-day window (+6.23%, SOL was actually UP +15.27% there - this
        # underperforms buy-and-hold in a rally, as expected for a defensive/
        # mean-reversion approach) AND a 1-year window (+3.24%, beating
        # buy-and-hold by +56.63% - SOL was down -53.39% there). LTCMYR was
        # also tested (4h and 1h, multiple windows) and REJECTED - no variant
        # showed a consistent sign across windows, the classic curve-fit
        # signature. Don't re-add LTC without a materially different
        # approach; see strategy_compare.py output in conversation history.
        # matches .github/workflows/sol_range_1h.yml's cron: "35 * * * *" (UTC)
        "schedule": {"interval_hours": 1, "minute_offset": 35},
    },
}


def apply_profile(cfg, name: str) -> dict:
    """Mutates the shared cfg module with this profile's overrides in
    place, and returns paths derived from the profile name."""
    if name not in PROFILES:
        raise ValueError(f"Unknown profile '{name}'. Choices: {list(PROFILES)}")
    overrides = PROFILES[name]
    for key, value in overrides.items():
        if key in ("label", "schedule"):
            continue
        setattr(cfg, key, value)
    return {
        "log_dir": f"logs/{name}",
        "state_file": f"state/{name}.json",
        "label": overrides.get("label", name),
    }
