"""
Logs every trade decision (including HOLDs, for auditing) with full
reasoning to a CSV, and can generate a plain-English performance
summary - this is the feedback loop meant to be reviewed weekly
(or fed back to Claude Code for rule tweaks).
"""

import csv
import os
from datetime import datetime, timezone


def log_event(log_dir: str, event: dict):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "trade_log.csv")
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "action", "price", "balance", "regime", "reason"
        ])
        if is_new:
            writer.writeheader()
        writer.writerow({
            "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "action": event.get("action"),
            "price": event.get("price"),
            "balance": event.get("balance"),
            "regime": event.get("regime"),
            "reason": event.get("reason"),
        })


def log_price(log_dir: str, price: float, regime: str, balance: float):
    """Logs the price seen on EVERY run (not just trades), so the dashboard
    can chart price over time with buy/sell markers. Started 2026-08-21 -
    won't have history from before that, it accumulates from here on."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "price_log.csv")
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "price", "regime", "balance"])
        if is_new:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": price, "regime": regime, "balance": balance,
        })


def summarize_performance(trades: list, starting_balance: float, ending_balance: float,
                           total_fees: float = None) -> str:
    """
    Plain-English summary of a run. `trades` is a list of dicts with
    at least: action, price, pnl (for closed trades). `pnl` is net of fees
    when the caller tracks fees (see backtest.py); `fee` on each trade dict
    is the individual leg's fee if present.
    """
    closed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    total_return_pct = ((ending_balance - starting_balance) / starting_balance * 100
                         if starting_balance else 0)

    lines = [
        f"Starting balance: {starting_balance:.2f}",
        f"Ending balance:   {ending_balance:.2f}",
        f"Total return:     {total_return_pct:+.2f}%",
        f"Total closed trades: {len(closed)}",
        f"Wins: {len(wins)}  Losses: {len(losses)}",
    ]
    if total_fees is not None:
        lines.append(f"Total fees paid: {total_fees:.2f} "
                      f"({total_fees / starting_balance * 100:.2f}% of starting balance)")
    if closed:
        win_rate = len(wins) / len(closed) * 100
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        lines.append(f"Win rate: {win_rate:.1f}%")
        lines.append(f"Avg win: {avg_win:.2f}  Avg loss: {avg_loss:.2f}")
    else:
        lines.append("No closed trades in this run yet.")

    return "\n".join(lines)
