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
        "label": "4h trend-following (10% trailing + dip-reentry)",
        "CANDLE_DURATION": 14400,
        "STOP_LOSS_PCT": 0.05,
        "TAKE_PROFIT_PCT": 0.08,  # superseded by TRAILING_STOP_PCT below - kept for reference/rollback
        "TRAILING_STOP_PCT": 0.10,
        "DIP_REENTRY_PCT": 0.06,
        "DIP_REENTRY_COOLDOWN_HOURS": 12,
        "DIP_REENTRY_CONFIRM_CANDLES": 3,
        # Updated 2026-09-01 after revalidate.py flagged all 5 profiles
        # UNDERPERFORMING buy-and-hold during the ongoing rally (this one by
        # -17.13pp on a 90-day window). Diagnosis: the fixed 8% take-profit
        # capped winners early, and a fresh full signal was too slow to
        # re-enter after a shakeout. Two changes, both re-tested on this
        # profile's own 90-day window AND a 1-year down-market window before
        # deploying:
        #   - TRAILING_STOP_PCT (replaces the fixed take-profit): widened
        #     8%->10% band tested 10-15%, all identical here - rides winners
        #     further instead of capping at +8%.
        #   - DIP_REENTRY_PCT (see core/dip_reentry.py): after a SELL, watches
        #     for a defined dip below the exit price then a REVERSAL
        #     CONFIRMATION (RSI turning up from oversold + 3 candles no
        #     longer making new lows) before re-entering - deliberately a
        #     stricter 3-candle confirmation than the 2-candle version first
        #     tried, which lost money; swept dip% 4-10% at confirm=3 and
        #     found a robust positive plateau at 5-7% on BOTH windows, not a
        #     single lucky point (cooldown 6-24h made no measurable
        #     difference at this candle duration).
        # Combined result: 90-day +2.65% -> +7.65% (rally capture nearly
        # tripled), 1-year down-market +5.96% -> +4.94% (a real but modest
        # give-back, still solidly positive). This is a genuine trade-off,
        # not a clean win on both windows - deployed anyway on 2026-09-01
        # since the down-market case stays clearly profitable either way and
        # the rally-capture gain is large. An ADX-based "strong trend
        # override" (dynamically widening stop-loss during very strong
        # trends) was also tested and REJECTED - showed no benefit beyond
        # plain trailing-stop widening and actively hurt sol_trend_4h.
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
    "sol_trend_4h": {
        "label": "SOLMYR 4h trend-following (min 2 signals, 10% trailing + dip-reentry)",
        "PAIR": "SOLMYR",
        "CANDLE_DURATION": 14400,
        "ALLOWED_REGIMES": ["trending"],
        "MIN_AGREEING_SIGNALS": 2,
        "TRAILING_STOP_PCT": 0.10,  # widened from 0.08 on 2026-09-01, see note below
        "DIP_REENTRY_PCT": 0.06,
        "DIP_REENTRY_COOLDOWN_HOURS": 12,
        "DIP_REENTRY_CONFIRM_CANDLES": 3,
        # Updated 2026-09-01: same round of testing as trend_4h (see its
        # comment above for the dip-reentry mechanism) after this profile was
        # also flagged UNDERPERFORMING (-28.06pp on a 90-day window) despite
        # already having a trailing stop. Widening 8%->10% alone was flat on
        # the 90-day window and +1.26pp on the 1-year window (non-negative on
        # both). Adding dip-reentry (dip 6%, cooldown 12h, confirm 3 candles -
        # same settings as trend_4h, not independently re-swept for this
        # pair) on top: 90-day +13.43%->+13.58% (marginal), 1-year
        # +7.86%->+10.31% (the strongest single result of anything tested
        # this round) - a clean improvement on BOTH windows, unlike trend_4h's
        # trade-off.
        #
        # STOP_LOSS_PCT left at config.py's default (3%) - untouched by
        # testing, still the hard downside floor. TRAILING_STOP_PCT replaces
        # the fixed TAKE_PROFIT_PCT (see core/risk.check_exit): rides the
        # position as long as price keeps making new highs, only exits once
        # price falls 10% back from the peak - built specifically because
        # sol_range_1h/range_1h_defensive/eth_range_4h/trend_4h all trailed
        # buy-and-hold badly during the 2026-08 rally (all 4 flagged
        # UNDERPERFORMING by revalidate.py on the same day this was added).
        #
        # Added 2026-08-31 as this project's first genuinely validated
        # trend-following profile, after two rounds of testing:
        #   - Round 1 mixed candle durations across the two validation windows
        #     (4h for the 1-year window, 1h for the 180-day window) and looked
        #     positive on both - WRONG methodology, caught before deploying.
        #   - Round 2 re-tested strictly on 4h candles for BOTH windows: +7.86%
        #     over a 1-year window where SOL fell -52.34% (beats buy-and-hold by
        #     +60.20pp), AND +8.81% over the last 180 days where SOL rallied
        #     +13.43% (trails buy-and-hold by only -4.62pp - far closer than any
        #     other profile/variant tested for any pair, which all trailed by
        #     15-30pp during the same rally). Also swept TRAILING_STOP_PCT from
        #     4% to 12% - positive and consistent across the whole 6-12% band,
        #     not a single lucky point (4-5% was borderline/negative on the
        #     1-year window, so this isn't a knife's-edge fit).
        # See strategy_compare.py's "trend_only min2 trailing N%" variants and
        # conversation history 2026-08-31 for the full sweep output before
        # touching this. Do NOT run this on 1h candles - that combination was
        # NOT validated (round 1's apparent 1h pass was the mixed-duration bug).
        "schedule": {"interval_hours": 4, "minute_offset": 50},
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
