from __future__ import annotations
<<<<<<< HEAD

from dataclasses import dataclass
from typing import Any, Dict
import pandas as pd

from utils.indicators import add_indicators


@dataclass
class Signal:
    symbol: str
    action: str
    score: int
    reason: str
    atr_value: float
    close_price: float
    ema_fast: float
    ema_slow: float
    rsi_value: float
    macd_hist: float
    volume_ratio: float
    breakout_up: bool
    breakout_down: bool
    regime: str
    htf_bias: int
    reasons: Dict[str, Any]
=======
import pandas as pd
import numpy as np


def ensure_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["open", "high", "low", "close", "vol"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna().reset_index(drop=True)
>>>>>>> 6a56521f62a913f472c7d729dcf97ff33da4d9ff


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

<<<<<<< HEAD
    def detect_regime(self, df: pd.DataFrame) -> str:
        last = df.iloc[-1]
        adx_val = float(last["adx"])
        bb_width = float(last["bb_width"])
        atr_val = float(last["atr"])
        close = float(last["close"])
        atr_pct = atr_val / close if close else 0
        if adx_val >= self.cfg.regime_adx_threshold:
            return "trend"
        if bb_width <= self.cfg.regime_bb_width_threshold and atr_pct < 0.012:
            return "range"
        return "volatile"

    def htf_bias(self, df_htf: pd.DataFrame) -> int:
        last = df_htf.iloc[-1]
        score = 0
        if last["ema_fast"] > last["ema_slow"]:
            score += 1
        elif last["ema_fast"] < last["ema_slow"]:
            score -= 1
        if last["rsi"] > 55:
            score += 1
        elif last["rsi"] < 45:
            score -= 1
        if last["macd_hist"] > 0:
            score += 1
        elif last["macd_hist"] < 0:
            score -= 1
        return score

    def fake_breakout_filter(self, df: pd.DataFrame, direction: str) -> bool:
        last = df.iloc[-1]
        prev_high = df["high"].iloc[-(self.cfg.breakout_lookback + 1):-1].max()
        prev_low = df["low"].iloc[-(self.cfg.breakout_lookback + 1):-1].min()
        if direction == "long":
            broke = last["high"] > prev_high
            closed_back_inside = last["close"] < prev_high
            bad_wick = last["upper_wick_ratio"] >= self.cfg.fake_breakout_wick_ratio
            return bool(broke and (closed_back_inside or bad_wick))
        if direction == "short":
            broke = last["low"] < prev_low
            closed_back_inside = last["close"] > prev_low
            bad_wick = last["lower_wick_ratio"] >= self.cfg.fake_breakout_wick_ratio
            return bool(broke and (closed_back_inside or bad_wick))
        return False

    def breakout_score(self, df: pd.DataFrame) -> tuple[int, bool, bool]:
        prev_high = df["high"].iloc[-(self.cfg.breakout_lookback + 1):-1].max()
        prev_low = df["low"].iloc[-(self.cfg.breakout_lookback + 1):-1].min()
        last = df.iloc[-1]
        breakout_up = bool(last["close"] > prev_high)
        breakout_down = bool(last["close"] < prev_low)
        if breakout_up:
            return 1, True, False
        if breakout_down:
            return -1, False, True
        return 0, False, False

    def volume_score(self, df: pd.DataFrame) -> tuple[int, float]:
        last = df.iloc[-1]
        avg_vol = df["vol"].iloc[-21:-1].mean()
        if avg_vol <= 0:
            return 0, 1.0
        ratio = float(last["vol"] / avg_vol)
        if ratio < self.cfg.volume_spike_threshold:
            return 0, ratio
        if last["close"] > last["open"]:
            return 1, ratio
        if last["close"] < last["open"]:
            return -1, ratio
        return 0, ratio

    def last_candle_too_extended(self, df: pd.DataFrame) -> bool:
        last = df.iloc[-1]
        atr_val = float(last["atr"])
        if atr_val <= 0:
            return False
        return float(last["range"] / atr_val) > self.cfg.max_last_candle_range_atr

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame | None = None) -> Signal:
        if df_htf is None:
            df_htf = df.copy()
        d = add_indicators(df, 9, 21, 14, self.cfg.atr_period)
        h = add_indicators(df_htf, 9, 21, 14, self.cfg.atr_period)
        if len(d) < 60 or len(h) < 60:
            price = float(d["close"].iloc[-1]) if len(d) else 0.0
            return Signal(symbol, "hold", 0, "not enough data", 0.0, price, 0.0, 0.0, 50.0, 0.0, 1.0, False, False, "insufficient_data", 0, {"error": "not enough data"})

        latest = d.iloc[-1]
        score = 0
        reasons: Dict[str, Any] = {}

        if latest["ema_fast"] > latest["ema_slow"]:
            score += 1
            reasons["ema"] = "bullish"
        elif latest["ema_fast"] < latest["ema_slow"]:
            score -= 1
            reasons["ema"] = "bearish"
        else:
            reasons["ema"] = "neutral"

        if latest["rsi"] > 55:
            score += 1
            reasons["rsi"] = f"bullish ({latest['rsi']:.2f})"
        elif latest["rsi"] < 45:
            score -= 1
            reasons["rsi"] = f"bearish ({latest['rsi']:.2f})"
        else:
            reasons["rsi"] = f"neutral ({latest['rsi']:.2f})"

        if latest["macd_hist"] > 0:
            score += 1
            reasons["macd"] = f"bullish ({latest['macd_hist']:.4f})"
        elif latest["macd_hist"] < 0:
            score -= 1
            reasons["macd"] = f"bearish ({latest['macd_hist']:.4f})"
        else:
            reasons["macd"] = "neutral"

        v_score, vol_ratio = self.volume_score(d)
        score += v_score
        reasons["volume"] = v_score

        b_score, breakout_up, breakout_down = self.breakout_score(d)
        score += b_score
        reasons["breakout"] = b_score

        regime = self.detect_regime(d)
        bias = self.htf_bias(h)
        reasons["htf_bias"] = bias
        if bias >= 2:
            score += 1
        elif bias <= -2:
            score -= 1

        if regime == "trend":
            if score >= 2:
                score += 1
            elif score <= -2:
                score -= 1
        elif regime == "range":
            if abs(score) < 3:
                score = 0
        elif regime == "volatile":
            if score > 0:
                score -= 1
            elif score < 0:
                score += 1

        price = float(latest["close"])
        atr_val = float(latest["atr"])

        if score >= self.cfg.aggressive_score_threshold and self.fake_breakout_filter(d, "long"):
            reasons["fake_breakout"] = "long rejected"
            return Signal(symbol, "hold", score, "fake breakout long", atr_val, price, float(latest["ema_fast"]), float(latest["ema_slow"]), float(latest["rsi"]), float(latest["macd_hist"]), vol_ratio, breakout_up, breakout_down, regime, bias, reasons)

        if score <= -self.cfg.aggressive_score_threshold and self.fake_breakout_filter(d, "short"):
            reasons["fake_breakout"] = "short rejected"
            return Signal(symbol, "hold", score, "fake breakout short", atr_val, price, float(latest["ema_fast"]), float(latest["ema_slow"]), float(latest["rsi"]), float(latest["macd_hist"]), vol_ratio, breakout_up, breakout_down, regime, bias, reasons)

        if self.last_candle_too_extended(d):
            reasons["overextended"] = "rejected"
            return Signal(symbol, "hold", score, "overextended candle", atr_val, price, float(latest["ema_fast"]), float(latest["ema_slow"]), float(latest["rsi"]), float(latest["macd_hist"]), vol_ratio, breakout_up, breakout_down, regime, bias, reasons)
=======

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd_hist(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
>>>>>>> 6a56521f62a913f472c7d729dcf97ff33da4d9ff

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().fillna(method="bfill")

<<<<<<< HEAD
        reason = ", ".join(f"{k}:{v}" for k, v in reasons.items()) if reasons else "No edge"
        return Signal(symbol, action, score, reason, atr_val, price, float(latest["ema_fast"]), float(latest["ema_slow"]), float(latest["rsi"]), float(latest["macd_hist"]), vol_ratio, breakout_up, breakout_down, regime, bias, reasons)
=======

def bollinger_width(series: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.Series:
    ma = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    upper = ma + std * std_mult
    lower = ma - std * std_mult
    width = (upper - lower) / ma.replace(0, np.nan)
    return width.fillna(0)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        (high - low),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

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


def add_indicators(
    df: pd.DataFrame,
    ema_fast_period: int,
    ema_slow_period: int,
    rsi_period: int,
    atr_period: int,
) -> pd.DataFrame:
    out = ensure_numeric(df)
    out["ema_fast"] = ema(out["close"], ema_fast_period)
    out["ema_slow"] = ema(out["close"], ema_slow_period)
    out["rsi"] = rsi(out["close"], rsi_period)
    out["macd_hist"] = macd_hist(out["close"])
    out["atr"] = atr(out, atr_period)
    out["bb_width"] = bollinger_width(out["close"])
    out["adx"] = adx(out)
    out = candle_stats(out)
    return out
>>>>>>> 6a56521f62a913f472c7d729dcf97ff33da4d9ff
