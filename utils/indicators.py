from __future__ import annotations

from typing import Tuple
import numpy as np
import pandas as pd


def ensure_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    if "volume" in out.columns and "vol" not in out.columns:
        rename["volume"] = "vol"
    out = out.rename(columns=rename)
    for col in ["open", "high", "low", "close", "vol"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna().reset_index(drop=True)


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill()


def bollinger_width(series: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.Series:
    ma = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    upper = ma + std * std_mult
    lower = ma - std * std_mult
    return ((upper - lower) / ma.replace(0, np.nan)).fillna(0)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_val = tr.rolling(period).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr_val)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(period).mean().fillna(0)


def candle_stats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["body"] = (out["close"] - out["open"]).abs()
    out["range"] = (out["high"] - out["low"]).replace(0, np.nan)
    out["upper_wick"] = out["high"] - out[["open", "close"]].max(axis=1)
    out["lower_wick"] = out[["open", "close"]].min(axis=1) - out["low"]
    out["upper_wick_ratio"] = (out["upper_wick"] / out["range"]).fillna(0)
    out["lower_wick_ratio"] = (out["lower_wick"] / out["range"]).fillna(0)
    return out


def add_indicators(df: pd.DataFrame, ema_fast_period: int = 9, ema_slow_period: int = 21, rsi_period: int = 14, atr_period: int = 14) -> pd.DataFrame:
    out = ensure_numeric(df)
    out["ema_fast"] = ema(out["close"], ema_fast_period)
    out["ema_slow"] = ema(out["close"], ema_slow_period)
    out["rsi"] = rsi(out["close"], rsi_period)
    _, _, out["macd_hist"] = macd(out["close"])
    out["atr"] = atr(out, atr_period)
    out["bb_width"] = bollinger_width(out["close"])
    out["adx"] = adx(out)
    out = candle_stats(out)
    out["volume"] = out["vol"]
    out["vol_sma"] = out["vol"].rolling(20).mean()
    return out
