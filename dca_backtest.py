"""
Backtests a Dollar-Cost-Averaging approach: buy a fixed MYR amount on a
fixed schedule (e.g. every N candles), regardless of any indicator signal,
and never sell - a DCA position is a long-term accumulation, not a trade.

This doesn't fit backtest.py's single-open-position model (that assumes you
enter fully and exit fully), so it's its own small harness. Fairly compared
against buy-and-hold-with-the-same-total-capital, and against the two
signal-based profiles' returns over the same window.

Usage:
    python dca_backtest.py data/real_candles_4h_2y.csv --every 42 --amount 5
    (--every is in candles - 42 candles * 4h = 1 week, on 4h-candle data)
"""

import argparse

import pandas as pd

import config as cfg

TAKER_FEE_PCT = getattr(cfg, "TAKER_FEE_PCT", 0.001)


def run_dca(csv_path: str, every_n_candles: int, amount_myr: float):
    df = pd.read_csv(csv_path)

    total_spent = 0.0
    total_units = 0.0
    total_fees = 0.0
    buys = 0

    for i in range(0, len(df), every_n_candles):
        price = df.iloc[i]["close"]
        fee = amount_myr * TAKER_FEE_PCT
        units = (amount_myr - fee) / price
        total_spent += amount_myr
        total_units += units
        total_fees += fee
        buys += 1

    final_price = df.iloc[-1]["close"]
    portfolio_value = total_units * final_price
    pnl = portfolio_value - total_spent
    pnl_pct = (pnl / total_spent * 100) if total_spent else 0

    # fair benchmark: same total capital, all in on day 1, no fee-drip
    bh_units = (total_spent - total_spent * TAKER_FEE_PCT) / df.iloc[0]["close"]
    bh_value = bh_units * final_price
    bh_pnl_pct = (bh_value - total_spent) / total_spent * 100

    print(f"DCA: {buys} buys of {amount_myr:.2f} MYR every {every_n_candles} candles")
    print(f"Total spent:      {total_spent:.2f} MYR")
    print(f"Total fees:       {total_fees:.2f} MYR")
    print(f"BTC accumulated:  {total_units:.8f}")
    print(f"Portfolio value:  {portfolio_value:.2f} MYR (at final price {final_price:.2f})")
    print(f"P/L:              {pnl:+.2f} MYR ({pnl_pct:+.2f}%)")
    print(f"vs lump-sum buy-and-hold of the same total capital: {bh_pnl_pct:+.2f}%")
    print(f"DCA vs lump-sum: {pnl_pct - bh_pnl_pct:+.2f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--every", type=int, default=42, help="buy every N candles")
    parser.add_argument("--amount", type=float, default=5.0, help="MYR per buy")
    args = parser.parse_args()
    run_dca(args.csv_path, args.every, args.amount)
