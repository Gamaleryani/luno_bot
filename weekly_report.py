"""
Consolidated weekly performance summary across every profile, emailed as a
plain-English digest. This reports on ACTUAL paper-trading results (real
trades already logged) - it's the "how did the bot actually do" report,
distinct from revalidate.py's "does the backtested edge still hold on
fresh data" check.

Usage:
    python weekly_report.py
"""

import csv
import os

import config as cfg
from core import notifier
from core.allocations import load_allocation
from core.profiles import PROFILES
from core.reports import compute_window_report


def load_trades(profile_name: str) -> list:
    path = os.path.join("logs", profile_name, "trade_log.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_balance(profile_name: str) -> float:
    import json
    path = os.path.join("state", f"{profile_name}.json")
    if not os.path.exists(path):
        return cfg.STARTING_BALANCE_MYR
    with open(path) as f:
        return json.load(f)["balance"]


if __name__ == "__main__":
    lines = ["Weekly luno_bot report", "=" * 40, ""]
    total_start = 0.0
    total_now = 0.0

    for name in PROFILES:
        label = PROFILES[name].get("label", name)
        allocation = load_allocation(name, cfg.STARTING_BALANCE_MYR)
        balance = load_balance(name)
        trades = load_trades(name)
        week = compute_window_report(trades, allocation, 24 * 7)

        total_start += allocation
        total_now += balance

        lines.append(f"{label} ({name})")
        lines.append(f"  Balance: {balance:.2f} MYR (started {allocation:.2f} MYR, "
                      f"{(balance - allocation) / allocation * 100:+.2f}% all-time)")
        if week["trade_count"] == 0:
            lines.append("  This week: no closed trades.")
        else:
            lines.append(f"  This week: {week['net_change']:+.2f} MYR, "
                          f"{week['trade_count']} closed ({week['wins']}W / {week['losses']}L)")
        lines.append("")

    total_pnl_pct = (total_now - total_start) / total_start * 100 if total_start else 0
    lines.append("-" * 40)
    lines.append(f"Combined: {total_now:.2f} MYR ({total_pnl_pct:+.2f}% all-time, "
                 f"started {total_start:.2f} MYR)")
    lines.append("")
    lines.append("Note: \"this week\" balance change includes capital now tied up in any "
                 "newly-opened position, not just realized trade profit - a net-negative "
                 "week can still include a real win if a new position opened afterward.")
    lines.append("Full detail: https://gamaleryani.github.io/luno_bot/")

    report = "\n".join(lines)
    print(report)
    notifier.notify("luno_bot weekly report", report)
