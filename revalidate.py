"""
Periodic check: does each live profile's deployed strategy still show an
edge over buy-and-hold on FRESH recent data? Every profile in
core/profiles.py was validated once against historical data before
deployment - markets change, so re-checking periodically catches an edge
that's quietly stopped working before it costs real money once live.

This does NOT auto-disable or change anything - it only notifies (push +
email if the deployed variant is now underperforming buy-and-hold on
recent data). Deciding whether to adjust or retire a profile from there is
a human call, same philosophy as the approval gate: inform, don't act
unilaterally on something this consequential.

Usage:
    python revalidate.py
"""

import importlib
import os

import config as cfg
from core import notifier
from core.luno_client import LunoClient
from core.profiles import apply_profile, PROFILES
from backtest import run_backtest
from data.fetch_history import fetch_history

RECENT_DAYS = 90
TMP_CSV = "state/_revalidate_tmp.csv"


def buy_and_hold_pct(df, fee_pct) -> float:
    start, end = df["close"].iloc[0], df["close"].iloc[-1]
    gross = (end - start) / start
    return (gross - 2 * fee_pct) * 100


if __name__ == "__main__":
    findings = []

    for name in PROFILES:
        importlib.reload(cfg)  # clean slate so a prior profile's overrides don't leak
        paths = apply_profile(cfg, name)
        client = LunoClient(cfg)

        try:
            df = fetch_history(client, cfg.PAIR, cfg.CANDLE_DURATION, RECENT_DAYS)
        except Exception as e:
            findings.append(f"{paths['label']} ({name}): FAILED to fetch fresh data - {e}")
            continue

        if len(df) < 30:
            findings.append(f"{paths['label']} ({name}): not enough recent candles "
                             f"({len(df)}) to re-check yet.")
            continue

        df.to_csv(TMP_CSV, index=False)
        balance, trades, fees = run_backtest(TMP_CSV, log=False, verbose=False)
        return_pct = (balance - cfg.STARTING_BALANCE_MYR) / cfg.STARTING_BALANCE_MYR * 100
        bh_pct = buy_and_hold_pct(df, getattr(cfg, "TAKER_FEE_PCT", 0.0))
        vs_bh = return_pct - bh_pct
        closed = [t for t in trades if t.get("pnl") is not None]

        status = "OK" if vs_bh >= 0 else "UNDERPERFORMING"
        line = (f"{paths['label']} ({name}): last {RECENT_DAYS}d - "
                f"{return_pct:+.2f}% ({len(closed)} trades) vs buy-and-hold "
                f"{bh_pct:+.2f}% -> {vs_bh:+.2f}% [{status}]")
        print(line)
        findings.append(line)

    if os.path.exists(TMP_CSV):
        os.remove(TMP_CSV)

    report = "luno_bot re-validation (last {}d)\n\n{}".format(RECENT_DAYS, "\n".join(findings))
    any_underperforming = any("UNDERPERFORMING" in f for f in findings)
    notifier.notify(
        f"luno_bot re-validation {'- CHECK NEEDED' if any_underperforming else 'OK'}",
        report,
        urgent=any_underperforming,
    )
