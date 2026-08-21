"""
Generates a synthetic BTC/MYR-like price series purely so the backtest
engine can be verified end-to-end before real Luno historical data is
pulled. NOT real market data - do not draw conclusions about strategy
performance from this, it's a plumbing test only.
"""

import numpy as np
import pandas as pd

np.random.seed(42)
n = 2000
start_price = 280000.0  # rough BTC/MYR scale
timestamps = pd.date_range("2026-01-01", periods=n, freq="5min").astype("int64") // 10**9

returns = np.random.normal(0, 0.002, n)
# inject a few trend/regime segments so ADX/regime logic has something to detect
returns[300:500] += 0.0015   # uptrend
returns[900:1100] -= 0.0015  # downtrend
prices = start_price * (1 + returns).cumprod()

high = prices * (1 + np.abs(np.random.normal(0, 0.001, n)))
low = prices * (1 - np.abs(np.random.normal(0, 0.001, n)))
open_ = np.roll(prices, 1)
open_[0] = start_price
volume = np.random.lognormal(mean=1, sigma=0.5, size=n)

df = pd.DataFrame({
    "timestamp": timestamps,
    "open": open_,
    "high": high,
    "low": low,
    "close": prices,
    "volume": volume,
})

df.to_csv("data/sample_candles.csv", index=False)
print(f"Wrote {len(df)} synthetic candles to data/sample_candles.csv")
