from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd

from utils.indicators import atr, ema, macd, rsi, adx, vwap


@dataclass
class Signal:
    symbol: str
    action: str
    score: int
    confidence: int
    regime: str
    reason: str
    profile: str
    atr_value: float
    close_price: float
    ema_fast: float
    ema_slow: float
    rsi_value: float
    macd_hist: float
    volume_ratio: float
    breakout_up: bool
    breakout_down: bool
    adx_value: float
    vwap_value: float
    htf_bias: int
    htf_sr_bias: int

    def to_dict(self):
        return asdict(self)


class StrategyEngine:
    def __init__(self, config):
        self.cfg = config

    def _prep(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["ema_fast"] = ema(d["close"], 9)
        d["ema_slow"] = ema(d["close"], 21)
        d["rsi"] = rsi(d["close"], 14)
        _, _, d["macd_hist"] = macd(d["close"])
        d["atr"] = atr(d, self.cfg.atr_period)
        d["vol_sma"] = d["volume"].rolling(20).mean()
        d["adx"] = adx(d, 14)
        d["vwap"] = vwap(d).bfill()
        d["body"] = (d["close"] - d["open"]).abs()
        d["range"] = (d["high"] - d["low"]).replace(0, 1e-9)
        d["upper_wick"] = d["high"] - d[["open", "close"]].max(axis=1)
        d["lower_wick"] = d[["open", "close"]].min(axis=1) - d["low"]
        d["upper_wick_ratio"] = d["upper_wick"] / d["range"]
        d["lower_wick_ratio"] = d["lower_wick"] / d["range"]
        return d

    def _profile(self, symbol: str) -> str:
        return "macro-index" if symbol.startswith("NAS100") else "macro-gold"

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame | None = None) -> Signal:
        d = self._prep(df)
        h = self._prep(df_htf) if df_htf is not None and len(df_htf) > 30 else None
        latest = d.iloc[-1]
        lookback = d.iloc[-(self.cfg.breakout_lookback + 1):-1]
        score = 0
        confidence = 50
        reasons: list[str] = []
        profile = self._profile(symbol)

        if latest["ema_fast"] > latest["ema_slow"]:
            score += 1
            confidence += 6
            reasons.append("EMA bullish")
        elif latest["ema_fast"] < latest["ema_slow"]:
            score -= 1
            confidence += 6
            reasons.append("EMA bearish")

        if latest["rsi"] > 57:
            score += 1
            confidence += 5
            reasons.append("RSI strong")
        elif latest["rsi"] < 43:
            score -= 1
            confidence += 5
            reasons.append("RSI weak")

        if latest["macd_hist"] > 0:
            score += 1
            confidence += 6
            reasons.append("MACD positive")
        elif latest["macd_hist"] < 0:
            score -= 1
            confidence += 6
            reasons.append("MACD negative")

        volume_ratio = float(latest["volume"] / latest["vol_sma"]) if latest["vol_sma"] else 1.0
        if volume_ratio > 1.2:
            confidence += 7
            if latest["close"] >= latest["open"]:
                score += 1
                reasons.append("Bullish volume")
            else:
                score -= 1
                reasons.append("Bearish volume")

        breakout_up = float(latest["close"]) > float(lookback["high"].max()) if not lookback.empty else False
        breakout_down = float(latest["close"]) < float(lookback["low"].min()) if not lookback.empty else False
        if breakout_up:
            score += 1
            confidence += 9
            reasons.append("Breakout up")
        if breakout_down:
            score -= 1
            confidence += 9
            reasons.append("Breakout down")

        adx_value = float(latest["adx"])
        vwap_value = float(latest["vwap"])
        regime = "trend" if adx_value >= self.cfg.adx_trend_threshold else "range"
        if float(latest["atr"] / latest["close"]) > 0.012:
            regime = "volatile"
        reasons.append(f"Regime {regime}")

        if regime == 'trend':
            confidence += 8
        elif regime == 'volatile':
            confidence -= 8
        else:
            confidence -= 2

        vwap_dist = abs(float(latest["close"] - vwap_value) / latest["close"])
        if vwap_dist > self.cfg.vwap_distance_limit:
            confidence -= 8
            if score > 0:
                score -= 1
            elif score < 0:
                score += 1
            reasons.append("VWAP stretched")

        htf_bias = 0
        htf_sr_bias = 0
        if h is not None:
            h_last = h.iloc[-1]
            if h_last["ema_fast"] > h_last["ema_slow"]:
                htf_bias += 1
            elif h_last["ema_fast"] < h_last["ema_slow"]:
                htf_bias -= 1
            if h_last["macd_hist"] > 0:
                htf_bias += 1
            elif h_last["macd_hist"] < 0:
                htf_bias -= 1
            h_lookback = h.iloc[-21:-1]
            if not h_lookback.empty:
                if float(latest["close"]) > float(h_lookback["high"].max()):
                    htf_sr_bias += 1
                elif float(latest["close"]) < float(h_lookback["low"].min()):
                    htf_sr_bias -= 1
            if htf_bias >= 2 and score > 0:
                score += 1
                confidence += 8
                reasons.append("HTF bullish")
            elif htf_bias <= -2 and score < 0:
                score -= 1
                confidence += 8
                reasons.append("HTF bearish")
            if htf_sr_bias != 0:
                confidence += 4

        fake_long = breakout_up and (latest["upper_wick_ratio"] > 0.45 or latest["close"] < lookback["high"].max()) if not lookback.empty else False
        fake_short = breakout_down and (latest["lower_wick_ratio"] > 0.45 or latest["close"] > lookback["low"].min()) if not lookback.empty else False
        if fake_long and score > 0:
            score -= 2
            confidence -= 18
            reasons.append("Fake breakout long")
        if fake_short and score < 0:
            score += 2
            confidence -= 18
            reasons.append("Fake breakout short")

        if profile == 'macro-index':
            if regime == 'trend' and abs(score) >= 2:
                confidence += 5
            if regime == 'range' and abs(score) >= 3:
                confidence -= 4
        elif profile == 'macro-gold':
            if regime == 'range' and abs(score) >= 2:
                confidence += 4
            if regime == 'volatile':
                confidence -= 5

        confidence = max(0, min(100, int(confidence)))

        action = "hold"
        if score >= self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            action = "long"
        elif score <= -self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            action = "short"

        return Signal(
            symbol=symbol,
            action=action,
            score=score,
            confidence=confidence,
            regime=regime,
            reason=", ".join(reasons) if reasons else "No edge",
            profile=profile,
            atr_value=float(latest["atr"]),
            close_price=float(latest["close"]),
            ema_fast=float(latest["ema_fast"]),
            ema_slow=float(latest["ema_slow"]),
            rsi_value=float(latest["rsi"]),
            macd_hist=float(latest["macd_hist"]),
            volume_ratio=volume_ratio,
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            adx_value=adx_value,
            vwap_value=vwap_value,
            htf_bias=htf_bias,
            htf_sr_bias=htf_sr_bias,
        )
