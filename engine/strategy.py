from __future__ import annotations

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


class StrategyEngine:
    def __init__(self, config):
        self.cfg = config

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

        action = "hold"
        if score >= self.cfg.aggressive_score_threshold:
            action = "long"
        elif score <= -self.cfg.aggressive_score_threshold:
            action = "short"

        reason = ", ".join(f"{k}:{v}" for k, v in reasons.items()) if reasons else "No edge"
        return Signal(symbol, action, score, reason, atr_val, price, float(latest["ema_fast"]), float(latest["ema_slow"]), float(latest["rsi"]), float(latest["macd_hist"]), vol_ratio, breakout_up, breakout_down, regime, bias, reasons)
