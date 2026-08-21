"""
Runs several structurally different strategy variants over the same
historical CSV and reports them side by side, so you can see which (if
any) survive real trading fees instead of tuning one variant blind.

Each variant temporarily overrides a few cfg attributes, runs the backtest
with logging disabled (so sweep runs don't pollute logs/trade_log.csv),
then restores the original config.

Usage:
    python strategy_compare.py data/real_candles_90d.csv
"""

import sys

import pandas as pd

import config as cfg
from backtest import run_backtest

VARIANTS = {
    "baseline (current)": {},
    "high_conviction (4/4 signals)": {"MIN_AGREEING_SIGNALS": 4},
    "wider_stops (5%/8%)": {"STOP_LOSS_PCT": 0.05, "TAKE_PROFIT_PCT": 0.08},
    "trend_only": {"ALLOWED_REGIMES": ["trending"]},
    "range_only": {"ALLOWED_REGIMES": ["ranging"]},
    "high_conviction + wider_stops": {
        "MIN_AGREEING_SIGNALS": 4, "STOP_LOSS_PCT": 0.05, "TAKE_PROFIT_PCT": 0.08,
    },
    "range_only, min2 signals": {
        "ALLOWED_REGIMES": ["ranging"], "MIN_AGREEING_SIGNALS": 2,
    },
    "range_only, min2, tight exits": {
        "ALLOWED_REGIMES": ["ranging"], "MIN_AGREEING_SIGNALS": 2,
        "STOP_LOSS_PCT": 0.02, "TAKE_PROFIT_PCT": 0.03,
    },
    "range_only, tight exits (min3)": {
        "ALLOWED_REGIMES": ["ranging"], "STOP_LOSS_PCT": 0.02, "TAKE_PROFIT_PCT": 0.03,
    },
    "very wide stops (10%/15%)": {"STOP_LOSS_PCT": 0.10, "TAKE_PROFIT_PCT": 0.15},
    "trend_only + wide stops": {
        "ALLOWED_REGIMES": ["trending"], "STOP_LOSS_PCT": 0.10, "TAKE_PROFIT_PCT": 0.15,
    },
    "swing (3%/5%)": {"STOP_LOSS_PCT": 0.03, "TAKE_PROFIT_PCT": 0.05},
    "swing (4%/6%)": {"STOP_LOSS_PCT": 0.04, "TAKE_PROFIT_PCT": 0.06},
    "swing trend_only (4%/6%)": {
        "ALLOWED_REGIMES": ["trending"], "STOP_LOSS_PCT": 0.04, "TAKE_PROFIT_PCT": 0.06,
    },
    "swing range_only (3%/5%)": {
        "ALLOWED_REGIMES": ["ranging"], "STOP_LOSS_PCT": 0.03, "TAKE_PROFIT_PCT": 0.05,
    },
}


def run_variant(csv_path: str, overrides: dict):
    original = {}
    for key, value in overrides.items():
        original[key] = getattr(cfg, key, None)
        setattr(cfg, key, value)

    balance, trades, total_fees = run_backtest(csv_path, log=False, verbose=False)

    for key, value in original.items():
        if value is None and key not in vars(cfg):
            delattr(cfg, key)
        else:
            setattr(cfg, key, value)

    closed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0
    return_pct = (balance - cfg.STARTING_BALANCE_MYR) / cfg.STARTING_BALANCE_MYR * 100
    holds = [t["hold_days"] for t in closed if t.get("hold_days") is not None]
    avg_hold_days = sum(holds) / len(holds) if holds else 0
    return {
        "return_pct": return_pct,
        "trades": len(closed),
        "win_rate": win_rate,
        "fees": total_fees,
        "ending_balance": balance,
        "avg_hold_days": avg_hold_days,
    }


def buy_and_hold_pct(csv_path: str) -> float:
    """What you'd have made just buying at the start and holding - the
    benchmark any active strategy needs to beat to justify existing."""
    df = pd.read_csv(csv_path)
    start_price, end_price = df["close"].iloc[0], df["close"].iloc[-1]
    fee_pct = getattr(cfg, "TAKER_FEE_PCT", 0.0)
    gross = (end_price - start_price) / start_price
    return (gross - 2 * fee_pct) * 100  # one fee in, one fee out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/real_candles_90d.csv"

    bh_pct = buy_and_hold_pct(path)
    print(f"Comparing {len(VARIANTS)} strategy variants on {path}")
    print(f"Buy-and-hold benchmark over this period: {bh_pct:+.2f}%\n")
    header = (f"{'Variant':<32}{'Return':>10}{'Trades':>9}{'Win rate':>11}"
              f"{'Fees paid':>11}{'Avg hold':>11}{'vs B&H':>10}")
    print(header)
    print("-" * len(header))

    results = {}
    for name, overrides in VARIANTS.items():
        r = run_variant(path, overrides)
        results[name] = r
        vs_bh = r["return_pct"] - bh_pct
        print(f"{name:<32}{r['return_pct']:>9.2f}%{r['trades']:>9}"
              f"{r['win_rate']:>10.1f}%{r['fees']:>10.2f}{r['avg_hold_days']:>9.1f}d{vs_bh:>+9.2f}%")

    best = max(results.items(), key=lambda kv: kv[1]["return_pct"])
    print(f"\nBest by return: {best[0]} ({best[1]['return_pct']:+.2f}%, "
          f"{best[1]['return_pct'] - bh_pct:+.2f}% vs buy-and-hold)")
