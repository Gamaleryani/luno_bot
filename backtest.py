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
from core import indicators, strategy, risk, logger


def run_backtest(csv_path: str, log: bool = True, verbose: bool = True):
    df = pd.read_csv(csv_path)
    df = indicators.compute_all(df, cfg)

    balance = cfg.STARTING_BALANCE_MYR
    position = None  # dict: entry_price, size
    trades = []
    total_fees = 0.0
    fee_pct = getattr(cfg, "TAKER_FEE_PCT", 0.0)

    warmup = max(cfg.MA_SLOW, cfg.BOLLINGER_PERIOD, cfg.ADX_PERIOD, cfg.RSI_PERIOD) + 1

    def close_position(price, reason, regime, timestamp=None):
        nonlocal balance, position, total_fees
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

    for i in range(warmup, len(df)):
        row = df.iloc[i]
        price = row["close"]

        # 1. manage any open position first (stop-loss / take-profit)
        if position is not None:
            exit_check = risk.check_exit(position["entry_price"], price, cfg,
                                          position.get("entry_timestamp"), row["timestamp"])
            if exit_check["exit"]:
                close_position(price, exit_check["reason"], "-", row["timestamp"])
                continue  # don't also evaluate a new entry same candle

        # 2. evaluate strategy for a new decision
        decision = strategy.evaluate(df, i, cfg)

        if decision["action"] == "BUY" and position is None:
            size_myr = risk.position_size(balance, row.get("atr", 0), price, cfg)
            fee = size_myr * fee_pct
            if size_myr > 0 and (size_myr + fee) <= balance:
                size_units = size_myr / price
                position = {"entry_price": price, "size_myr": size_myr, "size_units": size_units,
                            "entry_timestamp": row["timestamp"]}
                balance -= (size_myr + fee)
                total_fees += fee
                trades.append({"action": "BUY", "price": price, "pnl": None, "fee": fee,
                                "reason": decision["reason"]})
                if log:
                    logger.log_event(cfg.LOG_DIR, {
                        "timestamp": row["timestamp"], "action": "BUY", "price": price,
                        "balance": balance, "regime": decision["regime"], "reason": decision["reason"],
                    })

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
