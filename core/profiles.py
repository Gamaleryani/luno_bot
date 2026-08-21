"""
Named strategy profiles, so multiple configurations can run in parallel
against the same account without stepping on each other's logs/state.
Each profile overrides a few attributes on the shared `config` module and
gets its own log directory and state file.

Chosen from backtest comparison (see strategy_compare.py output,
2026-08-20): these two were the only configs that consistently beat a
buy-and-hold benchmark across multiple historical windows.
"""

PROFILES = {
    "trend_4h": {
        "label": "4h wider-stops (trend-friendly)",
        "CANDLE_DURATION": 14400,
        "STOP_LOSS_PCT": 0.05,
        "TAKE_PROFIT_PCT": 0.08,
    },
    "range_1h_defensive": {
        "label": "1h range-only tight exits (defensive)",
        "CANDLE_DURATION": 3600,
        "ALLOWED_REGIMES": ["ranging"],
        "STOP_LOSS_PCT": 0.02,
        "TAKE_PROFIT_PCT": 0.03,
    },
}


def apply_profile(cfg, name: str) -> dict:
    """Mutates the shared cfg module with this profile's overrides in
    place, and returns paths derived from the profile name."""
    if name not in PROFILES:
        raise ValueError(f"Unknown profile '{name}'. Choices: {list(PROFILES)}")
    overrides = PROFILES[name]
    for key, value in overrides.items():
        if key == "label":
            continue
        setattr(cfg, key, value)
    return {
        "log_dir": f"logs/{name}",
        "state_file": f"state/{name}.json",
        "label": overrides.get("label", name),
    }
