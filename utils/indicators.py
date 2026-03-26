from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    values = 100 - (100 / (1 + rs))
    return values.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    return pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period, min_periods=period).mean().bfill()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    tr = true_range(df)

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr_val = tr.rolling(period, min_periods=period).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(period, min_periods=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(period, min_periods=period).mean() / atr_val)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(period, min_periods=period).mean().fillna(0)


def rolling_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    pv_sum = pv.rolling(period, min_periods=1).sum()
    volume_sum = df["volume"].rolling(period, min_periods=1).sum().replace(0, np.nan)
    return (pv_sum / volume_sum).bfill()


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    volume_cumsum = df["volume"].replace(0, np.nan).cumsum()
    return (pv.cumsum() / volume_cumsum).bfill()
