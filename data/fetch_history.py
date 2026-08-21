"""
Pulls real historical candles from Luno and saves them as a CSV matching
the format backtest.py expects (timestamp,open,high,low,close,volume).

Requires LUNO_API_KEY_ID / LUNO_API_SECRET env vars (Luno's candles
endpoint now requires an authenticated key - a read-only key with no
trade/withdraw permission is enough, see core/luno_client.py).

Usage:
    python data/fetch_history.py --days 30
    python data/fetch_history.py --days 30 --pair XBTMYR --out data/real_candles.csv
"""

import argparse
import time

import pandas as pd

import config as cfg
from core.luno_client import LunoClient

MAX_CANDLES_PER_CALL = 1000  # Luno's documented cap per /candles request


def fetch_history(client: LunoClient, pair: str, duration: int, days: int) -> pd.DataFrame:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000
    span_per_call_ms = duration * 1000 * MAX_CANDLES_PER_CALL

    all_candles = []
    since = start_ms
    while since < end_ms:
        batch = client.get_candles(pair, duration, since)
        if not batch:
            break
        all_candles.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= since:
            break  # safety: avoid infinite loop if API doesn't advance
        since = last_ts + duration * 1000
        print(f"  fetched {len(batch)} candles, up to {pd.to_datetime(last_ts, unit='ms')}")
        time.sleep(0.5)  # be polite to the API

    if not all_candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_candles)
    df["timestamp"] = df["timestamp"] // 1000  # ms -> s, matches backtest.py's expectation
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="how many days of history to pull")
    parser.add_argument("--pair", type=str, default=cfg.PAIR)
    parser.add_argument("--duration", type=int, default=cfg.CANDLE_DURATION,
                         help="candle duration in seconds (e.g. 3600=1h, 14400=4h)")
    parser.add_argument("--out", type=str, default="data/real_candles.csv")
    args = parser.parse_args()

    client = LunoClient(cfg)
    print(f"Fetching {args.days}d of {args.pair} candles ({args.duration}s duration)...")
    df = fetch_history(client, args.pair, args.duration, args.days)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} real candles to {args.out}")
