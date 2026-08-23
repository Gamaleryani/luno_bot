"""
Computes plain-English daily/weekly summaries from a profile's trade_log.csv
for the dashboard. Walks the full trade history (not just the report window)
so a round-trip that started before the window but closed inside it is still
counted correctly, using each row's post-action balance to derive realized
P/L per closed trade.
"""

from datetime import datetime, timedelta, timezone


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_window_report(trades: list, starting_balance: float, window_hours: float) -> dict:
    """`trades` is the full trade_log.csv rows (dicts with timestamp/action/
    price/balance), oldest first."""
    if not trades:
        return {"trade_count": 0, "wins": 0, "losses": 0, "net_change": 0.0,
                "start_balance": None, "end_balance": None}

    now = _parse_ts(trades[-1]["timestamp"])
    since = now - timedelta(hours=window_hours)

    # `known_balance` tracks the last row's balance for BUY/SELL pairing
    # purposes and starts as None (unknown) - using the current allocation
    # as a stand-in for "balance before the very first logged row" is wrong
    # whenever allocation has changed since (e.g. a manual reset), so a
    # trade we can't honestly compute is skipped rather than mislabeled.
    # `last_balance`/`last_balance_before_window` are separate: they track
    # the window's overall net change, which the current allocation IS a
    # reasonable stand-in for when there's no visibility before all logged
    # history.
    known_balance = None
    pre_buy_balance = None
    last_balance_before_window = starting_balance
    last_balance = starting_balance
    trade_count = 0
    wins = 0
    losses = 0

    for row in trades:
        ts = _parse_ts(row["timestamp"])
        balance = float(row["balance"])
        in_window = ts >= since

        if row["action"] == "BUY":
            pre_buy_balance = known_balance
        elif row["action"] == "SELL":
            if in_window and pre_buy_balance is not None:
                pnl = balance - pre_buy_balance
                trade_count += 1
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                # pnl == 0 (breakeven) counts toward trade_count but neither
                # bucket - calling it a "loss" would be misleading
            pre_buy_balance = None

        known_balance = balance
        if not in_window:
            last_balance_before_window = balance
        last_balance = balance

    return {
        "trade_count": trade_count,
        "wins": wins,
        "losses": losses,
        "net_change": last_balance - last_balance_before_window,
        "start_balance": last_balance_before_window,
        "end_balance": last_balance,
    }
