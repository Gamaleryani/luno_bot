"""
Runs the multi-indicator strategy over historical candle data (CSV)
and reports how it would have performed - no network, no real money.

CSV format expected (columns): timestamp,open,high,low,close,volume

Usage:
    python backtest.py data/sample_candles.csv
"""

import sys
import pandas as pd

import config as cfg
from core import indicators, strategy, risk, logger, dip_reentry


def run_backtest(csv_path: str, log: bool = True, verbose: bool = True):
    df = pd.read_csv(csv_path)
    df = indicators.compute_all(df, cfg)

    balance = cfg.STARTING_BALANCE_MYR
    position = None  # dict: entry_price, size
    dip_watch = None  # set on every SELL, cleared the moment any new position opens
    trades = []
    total_fees = 0.0
    fee_pct = getattr(cfg, "TAKER_FEE_PCT", 0.0)

    warmup = max(cfg.MA_SLOW, cfg.BOLLINGER_PERIOD, cfg.ADX_PERIOD, cfg.RSI_PERIOD) + 1

    def close_position(price, reason, regime, timestamp=None):
        nonlocal balance, position, total_fees, dip_watch
        pnl = (price - position["entry_price"]) * position["size_units"]
        proceeds = position["size_myr"] + pnl
        fee = proceeds * fee_pct
        balance += proceeds - fee
        total_fees += fee
        hold_days = None
        if timestamp is not None and position.get("entry_timestamp") is not None:
            hold_days = (timestamp - position["entry_timestamp"]) / 86400
        trades.append({"action": "SELL", "price": price, "pnl": pnl - fee, "fee": fee,
                        "reason": reason, "hold_days": hold_days})
        if log and timestamp is not None:
            logger.log_event(cfg.LOG_DIR, {
                "timestamp": timestamp, "action": "SELL", "price": price,
                "balance": balance, "regime": regime, "reason": reason,
            })
        position = None
        dip_watch = dip_reentry.start_dip_watch(price, timestamp)

    def open_position(price, reason, regime, timestamp):
        nonlocal balance, position, total_fees, dip_watch
        size_myr = risk.position_size(balance, row.get("atr", 0), price, cfg)
        fee = size_myr * fee_pct
        if size_myr > 0 and (size_myr + fee) <= balance:
            size_units = size_myr / price
            position = {"entry_price": price, "size_myr": size_myr, "size_units": size_units,
                        "entry_timestamp": timestamp}
            balance -= (size_myr + fee)
            total_fees += fee
            dip_watch = None
            trades.append({"action": "BUY", "price": price, "pnl": None, "fee": fee, "reason": reason})
            if log:
                logger.log_event(cfg.LOG_DIR, {
                    "timestamp": timestamp, "action": "BUY", "price": price,
                    "balance": balance, "regime": regime, "reason": reason,
                })

    for i in range(warmup, len(df)):
        row = df.iloc[i]
        price = row["close"]

        # 1. manage any open position first (stop-loss / take-profit)
        if position is not None:
            position["peak_price"] = max(position.get("peak_price", position["entry_price"]), price)
            exit_check = risk.check_exit(position["entry_price"], price, cfg,
                                          position.get("entry_timestamp"), row["timestamp"],
                                          position.get("peak_price"), row.get("adx"))
            if exit_check["exit"]:
                close_position(price, exit_check["reason"], "-", row["timestamp"])
                continue  # don't also evaluate a new entry same candle

        # 2. flat: check dip re-entry first (cheaper, more specific), then
        # fall back to a normal fresh signal - either can open a position
        if position is None and dip_watch is not None:
            dip_reentry.update_dip_watch(dip_watch, price)
            redo = dip_reentry.check_dip_reentry(df, i, cfg, dip_watch, row["timestamp"])
            if redo["reentry"]:
                open_position(price, redo["reason"], "-", row["timestamp"])
                continue

        # 3. evaluate strategy for a new decision
        decision = strategy.evaluate(df, i, cfg)

        if decision["action"] == "BUY" and position is None:
            open_position(price, decision["reason"], decision["regime"], row["timestamp"])

        elif decision["action"] == "SELL" and position is not None:
            close_position(price, decision["reason"], decision["regime"], row["timestamp"])

    # close any still-open position at the last known price for accounting
    if position is not None:
        last_price = df.iloc[-1]["close"]
        close_position(last_price, "backtest ended - closing open position", "-",
                        df.iloc[-1]["timestamp"])

    summary = logger.summarize_performance(trades, cfg.STARTING_BALANCE_MYR, balance, total_fees)
    if verbose:
        print(summary)
    return balance, trades, total_fees


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_candles.csv"
    run_backtest(path)
