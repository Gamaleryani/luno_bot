"""
All indicator math lives here. Pure functions over a pandas DataFrame
with columns: timestamp, open, high, low, close, volume.
"""

import numpy as np
import pandas as pd


def add_rsi(df: pd.DataFrame, period: int) -> pd.DataFrame:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_moving_averages(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()
    return df


def add_bollinger_bands(df: pd.DataFrame, period: int, num_std: float) -> pd.DataFrame:
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_mid"] = mid
    df["bb_upper"] = mid + num_std * std
    df["bb_lower"] = mid - num_std * std
    return df


def add_volume_signal(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    avg_vol = df["volume"].rolling(lookback).mean()
    df["volume_ratio"] = df["volume"] / avg_vol.replace(0, np.nan)
    return df


def add_adx(df: pd.DataFrame, period: int) -> pd.DataFrame:
    """Average Directional Index - measures trend strength (not direction)."""
    high, low, close = df["high"], df["low"], df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm - minus_dm) < 0] = 0
    minus_dm[(minus_dm - plus_dm) < 0] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.rolling(period).mean()
    df["atr"] = atr
    return df


def compute_all(df: pd.DataFrame, cfg) -> pd.DataFrame:
    df = df.copy()
    df = add_rsi(df, cfg.RSI_PERIOD)
    df = add_moving_averages(df, cfg.MA_FAST, cfg.MA_SLOW)
    df = add_bollinger_bands(df, cfg.BOLLINGER_PERIOD, cfg.BOLLINGER_STD)
    df = add_volume_signal(df, cfg.VOLUME_LOOKBACK)
    df = add_adx(df, cfg.ADX_PERIOD)
    return df
