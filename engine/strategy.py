from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from utils.indicators import adx, atr, ema, macd, rolling_vwap, rsi, vwap


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

    def determine_action(self, score: int, confidence: int, regime: str | None = None) -> str:
        if self.cfg.require_trending_regime and regime is not None and regime != "trend":
            return "hold"
        if score >= self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            return "long"
        if score <= -self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            return "short"
        return "hold"

    def _prep(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["ema_fast"] = ema(d["close"], 9)
        d["ema_slow"] = ema(d["close"], 21)
        d["ema_trend"] = ema(d["close"], 55)
        d["rsi"] = rsi(d["close"], 14)
        _, _, d["macd_hist"] = macd(d["close"])
        d["atr"] = atr(d, self.cfg.atr_period)
        d["vol_sma"] = d["volume"].rolling(20, min_periods=5).mean().bfill()
        d["adx"] = adx(d, 14)
        d["vwap"] = vwap(d).bfill()
        d["rolling_vwap"] = rolling_vwap(d, 20).bfill()
        d["body"] = (d["close"] - d["open"]).abs()
        d["range"] = (d["high"] - d["low"]).replace(0, 1e-9)
        d["upper_wick"] = d["high"] - d[["open", "close"]].max(axis=1)
        d["lower_wick"] = d[["open", "close"]].min(axis=1) - d["low"]
        d["upper_wick_ratio"] = d["upper_wick"] / d["range"]
        d["lower_wick_ratio"] = d["lower_wick"] / d["range"]
        d["ema_diff"] = d["ema_fast"] - d["ema_slow"]
        return d

    def _profile(self, symbol: str) -> str:
        return "macro-index" if symbol.startswith("NAS100") else "macro-gold"

    def _weights(self, profile: str) -> dict[str, float]:
        if profile == "macro-index":
            return {
                "trend": 1.35,
                "mean_reversion": 0.85,
                "breakout": 1.25,
                "volume": 1.0,
            }
        return {
            "trend": 1.0,
            "mean_reversion": 1.2,
            "breakout": 0.95,
            "volume": 0.9,
        }

    def _recent_cross_bonus(self, d: pd.DataFrame) -> int:
        recent = d["ema_diff"].iloc[-4:]
        if len(recent) < 2:
            return 0
        bullish = ((recent.shift(1) <= 0) & (recent > 0)).iloc[-3:].any()
        bearish = ((recent.shift(1) >= 0) & (recent < 0)).iloc[-3:].any()
        if bullish:
            return 1
        if bearish:
            return -1
        return 0

    def _sr_levels(self, d: pd.DataFrame) -> tuple[float | None, float | None]:
        window = d.iloc[-(self.cfg.sr_lookback + 1):-1]
        if window.empty:
            return None, None
        return float(window["low"].min()), float(window["high"].max())

    def _rsi_divergence(self, d: pd.DataFrame) -> int:
        recent = d.iloc[-(self.cfg.rsi_divergence_lookback + 2):]
        if len(recent) < 4:
            return 0
        latest = recent.iloc[-1]
        prior = recent.iloc[:-1]

        low_idx = prior["low"].idxmin()
        high_idx = prior["high"].idxmax()
        prior_low = prior.loc[low_idx]
        prior_high = prior.loc[high_idx]

        bullish = (
            float(latest["low"]) < float(prior_low["low"])
            and float(latest["rsi"]) > float(prior_low["rsi"]) + self.cfg.rsi_divergence_min_delta
        )
        bearish = (
            float(latest["high"]) > float(prior_high["high"])
            and float(latest["rsi"]) < float(prior_high["rsi"]) - self.cfg.rsi_divergence_min_delta
        )
        if bullish:
            return 2
        if bearish:
            return -2
        return 0

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame | None = None) -> Signal:
        d = self._prep(df)
        h = self._prep(df_htf) if df_htf is not None and len(df_htf) > 40 else None
        latest = d.iloc[-1]
        lookback = d.iloc[-(self.cfg.breakout_lookback + 1):-1]
        profile = self._profile(symbol)
        weights = self._weights(profile)
        score = 0.0
        confidence = 34.0
        reasons: list[str] = []

        ema_fast = float(latest["ema_fast"])
        ema_slow = float(latest["ema_slow"])
        ema_trend = float(latest["ema_trend"])
        close_price = float(latest["close"])
        atr_value = float(latest["atr"]) if float(latest["atr"]) > 0 else close_price * 0.004

        if ema_fast > ema_slow > ema_trend:
            score += 2.0 * weights["trend"]
            confidence += 9
            reasons.append("EMA stack bullish")
        elif ema_fast < ema_slow < ema_trend:
            score -= 2.0 * weights["trend"]
            confidence += 9
            reasons.append("EMA stack bearish")
        elif ema_fast > ema_slow:
            score += 1.0 * weights["trend"]
            confidence += 5
            reasons.append("EMA bullish")
        elif ema_fast < ema_slow:
            score -= 1.0 * weights["trend"]
            confidence += 5
            reasons.append("EMA bearish")

        cross_bonus = self._recent_cross_bonus(d)
        if cross_bonus > 0:
            score += 1.0 * weights["trend"]
            confidence += 4
            reasons.append("Recent bullish cross")
        elif cross_bonus < 0:
            score -= 1.0 * weights["trend"]
            confidence += 4
            reasons.append("Recent bearish cross")

        ema_gap_pct = abs(ema_fast - ema_slow) / close_price if close_price else 0.0
        if ema_gap_pct > self.cfg.ema_distance_threshold:
            gap_weight = 2 if ema_gap_pct > self.cfg.ema_distance_threshold * 2 else 1
            if ema_fast > ema_slow:
                score += gap_weight * weights["trend"]
                reasons.append("EMA momentum up")
            else:
                score -= gap_weight * weights["trend"]
                reasons.append("EMA momentum down")
            confidence += 3 + gap_weight

        rsi_value = float(latest["rsi"])
        if rsi_value > 58:
            score += 1.0
            confidence += 5
            reasons.append("RSI strength")
        elif rsi_value < 42:
            score -= 1.0
            confidence += 5
            reasons.append("RSI weakness")

        divergence = self._rsi_divergence(d)
        if divergence > 0:
            score += 2.0 * weights["mean_reversion"]
            confidence += 6
            reasons.append("Bullish RSI divergence")
        elif divergence < 0:
            score -= 2.0 * weights["mean_reversion"]
            confidence += 6
            reasons.append("Bearish RSI divergence")

        macd_hist = float(latest["macd_hist"])
        if macd_hist > 0:
            score += 1.0
            confidence += 5
            reasons.append("MACD positive")
        elif macd_hist < 0:
            score -= 1.0
            confidence += 5
            reasons.append("MACD negative")

        volume_ratio = float(latest["volume"] / latest["vol_sma"]) if float(latest["vol_sma"]) > 0 else 1.0
        if volume_ratio > 1.15:
            confidence += 5
            if latest["close"] >= latest["open"]:
                score += 1.0 * weights["volume"]
                reasons.append("Bullish volume")
            else:
                score -= 1.0 * weights["volume"]
                reasons.append("Bearish volume")

        breakout_up = float(latest["close"]) > float(lookback["high"].max()) if not lookback.empty else False
        breakout_down = float(latest["close"]) < float(lookback["low"].min()) if not lookback.empty else False
        if breakout_up:
            score += 1.5 * weights["breakout"]
            confidence += 7
            reasons.append("Breakout up")
        if breakout_down:
            score -= 1.5 * weights["breakout"]
            confidence += 7
            reasons.append("Breakout down")

        support_level, resistance_level = self._sr_levels(d)
        if support_level is not None and atr_value > 0:
            support_distance = (close_price - support_level) / atr_value
            if 0 <= support_distance <= self.cfg.sr_atr_tolerance and latest["close"] >= latest["open"]:
                score += 1.5 * weights["mean_reversion"]
                confidence += 6
                reasons.append("Support reaction")
        if resistance_level is not None and atr_value > 0:
            resistance_distance = (resistance_level - close_price) / atr_value
            if 0 <= resistance_distance <= self.cfg.sr_atr_tolerance and latest["close"] <= latest["open"]:
                score -= 1.5 * weights["mean_reversion"]
                confidence += 6
                reasons.append("Resistance reaction")

        adx_value = float(latest["adx"])
        atr_pct = atr_value / close_price if close_price else 0.0
        if atr_pct >= self.cfg.volatile_atr_ratio:
            regime = "volatile"
        elif adx_value >= self.cfg.adx_trend_threshold:
            regime = "trend"
        else:
            regime = "range"
        reasons.append(f"Regime {regime}")

        if regime == "trend":
            confidence += 7
        elif regime == "range":
            confidence += 1 if profile == "macro-gold" else -2
        else:
            confidence -= 3
            if profile == "macro-gold":
                confidence -= 2

        vwap_value = float(latest["rolling_vwap"])
        if close_price > vwap_value:
            score += 0.75
            reasons.append("Above rolling VWAP")
        elif close_price < vwap_value:
            score -= 0.75
            reasons.append("Below rolling VWAP")

        vwap_dist = abs((close_price - vwap_value) / close_price) if close_price else 0.0
        if vwap_dist > self.cfg.vwap_distance_limit:
            confidence -= 7
            if score > 0:
                score -= 0.75
            elif score < 0:
                score += 0.75
            reasons.append("VWAP stretched")

        fake_long = breakout_up and (latest["upper_wick_ratio"] > 0.45 or latest["close"] < lookback["high"].max()) if not lookback.empty else False
        fake_short = breakout_down and (latest["lower_wick_ratio"] > 0.45 or latest["close"] > lookback["low"].min()) if not lookback.empty else False
        if fake_long and score > 0:
            score -= 2.0
            confidence -= 14
            reasons.append("Fake breakout long")
        if fake_short and score < 0:
            score += 2.0
            confidence -= 14
            reasons.append("Fake breakout short")

        htf_bias = 0
        htf_sr_bias = 0
        if h is not None:
            h_last = h.iloc[-1]
            if float(h_last["ema_fast"]) > float(h_last["ema_slow"]) > float(h_last["ema_trend"]):
                htf_bias = 2
            elif float(h_last["ema_fast"]) < float(h_last["ema_slow"]) < float(h_last["ema_trend"]):
                htf_bias = -2

            h_lookback = h.iloc[-(self.cfg.sr_lookback + 1):-1]
            if not h_lookback.empty:
                h_support = float(h_lookback["low"].min())
                h_resistance = float(h_lookback["high"].max())
                if close_price <= h_support + atr_value * self.cfg.sr_atr_tolerance:
                    htf_sr_bias = 1
                elif close_price >= h_resistance - atr_value * self.cfg.sr_atr_tolerance:
                    htf_sr_bias = -1

            if htf_bias > 0 and score > 0:
                score += 1.5
                confidence += 7
                reasons.append("HTF bullish alignment")
            elif htf_bias < 0 and score < 0:
                score -= 1.5
                confidence += 7
                reasons.append("HTF bearish alignment")

            if htf_sr_bias > 0 and score >= 0:
                score += 0.5
            elif htf_sr_bias < 0 and score <= 0:
                score -= 0.5

        confidence += min(abs(score) * 1.5, 10)
        confidence = max(0, min(100, int(round(confidence))))
        score_int = int(round(score))
        action = self.determine_action(score_int, confidence, regime)

        return Signal(
            symbol=symbol,
            action=action,
            score=score_int,
            confidence=confidence,
            regime=regime,
            reason=", ".join(reasons) if reasons else "No edge",
            profile=profile,
            atr_value=atr_value,
            close_price=close_price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi_value=rsi_value,
            macd_hist=macd_hist,
            volume_ratio=volume_ratio,
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            adx_value=adx_value,
            vwap_value=vwap_value,
            htf_bias=htf_bias,
            htf_sr_bias=htf_sr_bias,
        )
