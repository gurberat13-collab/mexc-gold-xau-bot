from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

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
    model: str = "base"
    target_price: float | None = None
    target_label: str | None = None
    sweep_side: str | None = None
    cisd_detected: bool = False
    asia_high: float | None = None
    asia_low: float | None = None
    first_fvg_side: str | None = None

    def to_dict(self):
        return asdict(self)


class StrategyEngine:
    def __init__(self, config):
        self.cfg = config
        self.ny_tz     = ZoneInfo(self.cfg.ny_timezone)
        self.london_tz = ZoneInfo("Europe/London")

    # ------------------------------------------------------------------ #
    # Action decider
    # ------------------------------------------------------------------ #

    def determine_action(self, score: int, confidence: int, regime: str | None = None) -> str:
        if self.cfg.require_trending_regime and regime is not None and regime != "trend":
            return "hold"
        if score >= self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            return "long"
        if score <= -self.cfg.mode_threshold() and confidence >= self.cfg.mode_confidence_min():
            return "short"
        return "hold"

    # ------------------------------------------------------------------ #
    # Data prep
    # ------------------------------------------------------------------ #

    def _prep(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["ema_fast"]     = ema(d["close"], 9)
        d["ema_slow"]     = ema(d["close"], 21)
        d["ema_trend"]    = ema(d["close"], 55)
        d["rsi"]          = rsi(d["close"], 14)
        _, _, d["macd_hist"] = macd(d["close"])
        d["atr"]          = atr(d, self.cfg.atr_period)
        d["vol_sma"]      = d["volume"].rolling(20, min_periods=5).mean().bfill()
        d["adx"]          = adx(d, 14)
        d["vwap"]         = vwap(d).bfill()
        d["rolling_vwap"] = rolling_vwap(d, 20).bfill()
        d["body"]         = (d["close"] - d["open"]).abs()
        d["range"]        = (d["high"] - d["low"]).replace(0, 1e-9)
        d["upper_wick"]   = d["high"] - d[["open", "close"]].max(axis=1)
        d["lower_wick"]   = d[["open", "close"]].min(axis=1) - d["low"]
        d["upper_wick_ratio"] = d["upper_wick"] / d["range"]
        d["lower_wick_ratio"] = d["lower_wick"] / d["range"]
        d["ema_diff"]     = d["ema_fast"] - d["ema_slow"]
        return d

    def _profile(self, symbol: str) -> str:
        return "macro-index" if symbol.startswith("NAS100") else "macro-gold"

    def _weights(self, profile: str) -> dict[str, float]:
        if profile == "macro-index":
            return {"trend": 1.35, "mean_reversion": 0.85, "breakout": 1.25, "volume": 1.0}
        return {"trend": 1.0, "mean_reversion": 1.2, "breakout": 0.95, "volume": 0.9}

    # ------------------------------------------------------------------ #
    # Time helpers
    # ------------------------------------------------------------------ #

    def _ensure_utc(self, value) -> datetime:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _reference_time(self, df: pd.DataFrame) -> datetime:
        return self._ensure_utc(df.iloc[-1]["time"])

    def _parse_clock(self, value: str) -> time:
        hour, minute = (value.split(":") + ["0"])[:2]
        return time(int(hour), int(minute))

    def _window_bounds_tz(self, reference_time: datetime, window_text: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
        ref_local   = self._ensure_utc(reference_time).astimezone(tz)
        start_text, end_text = [c.strip() for c in window_text.split("-")]
        start_clock = self._parse_clock(start_text)
        end_clock   = self._parse_clock(end_text)
        if start_clock <= end_clock:
            start_date = end_date = ref_local.date()
        else:
            if ref_local.time() <= end_clock:
                start_date = ref_local.date() - timedelta(days=1)
                end_date   = ref_local.date()
            else:
                start_date = ref_local.date()
                end_date   = ref_local.date() + timedelta(days=1)
        start_dt = datetime.combine(start_date, start_clock, tzinfo=tz)
        end_dt   = datetime.combine(end_date,   end_clock,   tzinfo=tz)
        return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc)

    def _window_bounds_ny(self, reference_time, window_text):
        return self._window_bounds_tz(reference_time, window_text, self.ny_tz)

    def _slice_window_ny(self, df, reference_time, window_text):
        s, e = self._window_bounds_ny(reference_time, window_text)
        return df[(df["time"] >= s) & (df["time"] <= e)].copy()

    def _slice_window_london(self, df, reference_time, window_text):
        s, e = self._window_bounds_tz(reference_time, window_text, self.london_tz)
        return df[(df["time"] >= s) & (df["time"] <= e)].copy()

    def _in_any_window_ny(self, reference_time: datetime, windows_text: str) -> bool:
        for window_text in windows_text.split(","):
            if not window_text.strip():
                continue
            s, e = self._window_bounds_ny(reference_time, window_text.strip())
            if s <= self._ensure_utc(reference_time) <= e:
                return True
        return False

    def _in_any_window_london(self, reference_time: datetime, windows_text: str) -> bool:
        for window_text in windows_text.split(","):
            if not window_text.strip():
                continue
            s, e = self._window_bounds_tz(reference_time, window_text.strip(), self.london_tz)
            if s <= self._ensure_utc(reference_time) <= e:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Sub-indicators
    # ------------------------------------------------------------------ #

    def _recent_cross_bonus(self, d: pd.DataFrame) -> int:
        recent = d["ema_diff"].iloc[-4:]
        if len(recent) < 2:
            return 0
        bullish = ((recent.shift(1) <= 0) & (recent > 0)).iloc[-3:].any()
        bearish = ((recent.shift(1) >= 0) & (recent < 0)).iloc[-3:].any()
        return 1 if bullish else (-1 if bearish else 0)

    def _sr_levels(self, d: pd.DataFrame) -> tuple[float | None, float | None]:
        window = d.iloc[-(self.cfg.sr_lookback + 1):-1]
        if window.empty:
            return None, None
        return float(window["low"].min()), float(window["high"].max())

    def _rsi_divergence(self, d: pd.DataFrame) -> int:
        recent = d.iloc[-(self.cfg.rsi_divergence_lookback + 2):]
        if len(recent) < 4:
            return 0
        latest     = recent.iloc[-1]
        prior      = recent.iloc[:-1]
        low_idx    = prior["low"].idxmin()
        high_idx   = prior["high"].idxmax()
        prior_low  = prior.loc[low_idx]
        prior_high = prior.loc[high_idx]
        bullish = (float(latest["low"])  < float(prior_low["low"])  and
                   float(latest["rsi"]) > float(prior_low["rsi"])  + self.cfg.rsi_divergence_min_delta)
        bearish = (float(latest["high"]) > float(prior_high["high"]) and
                   float(latest["rsi"]) < float(prior_high["rsi"]) - self.cfg.rsi_divergence_min_delta)
        if bullish:
            return 2
        if bearish:
            return -2
        return 0

    # ------------------------------------------------------------------ #
    # Base analysis (indicator scoring)
    # ------------------------------------------------------------------ #

    def _analyze_base(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame | None = None) -> Signal:
        d = self._prep(df)
        h = self._prep(df_htf) if df_htf is not None and len(df_htf) > 40 else None
        latest    = d.iloc[-1]
        lookback  = d.iloc[-(self.cfg.breakout_lookback + 1):-1]
        profile   = self._profile(symbol)
        weights   = self._weights(profile)
        score     = 0.0
        confidence = 34.0
        reasons: list[str] = []

        ema_fast    = float(latest["ema_fast"])
        ema_slow    = float(latest["ema_slow"])
        ema_trend   = float(latest["ema_trend"])
        close_price = float(latest["close"])
        atr_value   = float(latest["atr"]) if float(latest["atr"]) > 0 else close_price * 0.004

        # EMA stack
        if ema_fast > ema_slow > ema_trend:
            score += 2.0 * weights["trend"]; confidence += 9; reasons.append("EMA stack bullish")
        elif ema_fast < ema_slow < ema_trend:
            score -= 2.0 * weights["trend"]; confidence += 9; reasons.append("EMA stack bearish")
        elif ema_fast > ema_slow:
            score += 1.0 * weights["trend"]; confidence += 5; reasons.append("EMA bullish")
        elif ema_fast < ema_slow:
            score -= 1.0 * weights["trend"]; confidence += 5; reasons.append("EMA bearish")

        cross = self._recent_cross_bonus(d)
        if cross > 0:
            score += 1.0 * weights["trend"]; confidence += 4; reasons.append("Recent bullish cross")
        elif cross < 0:
            score -= 1.0 * weights["trend"]; confidence += 4; reasons.append("Recent bearish cross")

        ema_gap_pct = abs(ema_fast - ema_slow) / close_price if close_price else 0.0
        if ema_gap_pct > self.cfg.ema_distance_threshold:
            gap_w = 2 if ema_gap_pct > self.cfg.ema_distance_threshold * 2 else 1
            if ema_fast > ema_slow:
                score += gap_w * weights["trend"]; reasons.append("EMA momentum up")
            else:
                score -= gap_w * weights["trend"]; reasons.append("EMA momentum down")
            confidence += 3 + gap_w

        rsi_value = float(latest["rsi"])
        if rsi_value > 58:
            score += 1.0; confidence += 5; reasons.append("RSI strength")
        elif rsi_value < 42:
            score -= 1.0; confidence += 5; reasons.append("RSI weakness")

        div = self._rsi_divergence(d)
        if div > 0:
            score += 2.0 * weights["mean_reversion"]; confidence += 6; reasons.append("Bullish RSI divergence")
        elif div < 0:
            score -= 2.0 * weights["mean_reversion"]; confidence += 6; reasons.append("Bearish RSI divergence")

        macd_hist = float(latest["macd_hist"])
        if macd_hist > 0:
            score += 1.0; confidence += 5; reasons.append("MACD positive")
        elif macd_hist < 0:
            score -= 1.0; confidence += 5; reasons.append("MACD negative")

        volume_ratio = float(latest["volume"] / latest["vol_sma"]) if float(latest["vol_sma"]) > 0 else 1.0
        if volume_ratio > 1.15:
            confidence += 5
            if latest["close"] >= latest["open"]:
                score += 1.0 * weights["volume"]; reasons.append("Bullish volume")
            else:
                score -= 1.0 * weights["volume"]; reasons.append("Bearish volume")

        breakout_up   = float(latest["close"]) > float(lookback["high"].max()) if not lookback.empty else False
        breakout_down = float(latest["close"]) < float(lookback["low"].min())  if not lookback.empty else False
        if breakout_up:
            score += 1.5 * weights["breakout"]; confidence += 7; reasons.append("Breakout up")
        if breakout_down:
            score -= 1.5 * weights["breakout"]; confidence += 7; reasons.append("Breakout down")

        support_level, resistance_level = self._sr_levels(d)
        if support_level is not None and atr_value > 0:
            dist = (close_price - support_level) / atr_value
            if 0 <= dist <= self.cfg.sr_atr_tolerance and latest["close"] >= latest["open"]:
                score += 1.5 * weights["mean_reversion"]; confidence += 6; reasons.append("Support reaction")
        if resistance_level is not None and atr_value > 0:
            dist = (resistance_level - close_price) / atr_value
            if 0 <= dist <= self.cfg.sr_atr_tolerance and latest["close"] <= latest["open"]:
                score -= 1.5 * weights["mean_reversion"]; confidence += 6; reasons.append("Resistance reaction")

        adx_value = float(latest["adx"])
        atr_pct   = atr_value / close_price if close_price else 0.0
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
            score += 0.75; reasons.append("Above rolling VWAP")
        elif close_price < vwap_value:
            score -= 0.75; reasons.append("Below rolling VWAP")
        vwap_dist = abs((close_price - vwap_value) / close_price) if close_price else 0.0
        if vwap_dist > self.cfg.vwap_distance_limit:
            confidence -= 7
            score = score - 0.75 if score > 0 else score + 0.75
            reasons.append("VWAP stretched")

        fake_long  = breakout_up  and (latest["upper_wick_ratio"] > 0.45 or latest["close"] < lookback["high"].max()) if not lookback.empty else False
        fake_short = breakout_down and (latest["lower_wick_ratio"] > 0.45 or latest["close"] > lookback["low"].min())  if not lookback.empty else False
        if fake_long  and score > 0: score -= 2.0; confidence -= 14; reasons.append("Fake breakout long")
        if fake_short and score < 0: score += 2.0; confidence -= 14; reasons.append("Fake breakout short")

        htf_bias = htf_sr_bias = 0
        if h is not None:
            h_last = h.iloc[-1]
            if float(h_last["ema_fast"]) > float(h_last["ema_slow"]) > float(h_last["ema_trend"]):
                htf_bias = 2
            elif float(h_last["ema_fast"]) < float(h_last["ema_slow"]) < float(h_last["ema_trend"]):
                htf_bias = -2
            h_lookback = h.iloc[-(self.cfg.sr_lookback + 1):-1]
            if not h_lookback.empty:
                h_sup = float(h_lookback["low"].min())
                h_res = float(h_lookback["high"].max())
                if close_price <= h_sup + atr_value * self.cfg.sr_atr_tolerance:
                    htf_sr_bias = 1
                elif close_price >= h_res - atr_value * self.cfg.sr_atr_tolerance:
                    htf_sr_bias = -1
            if htf_bias > 0 and score > 0:
                score += 1.5; confidence += 7; reasons.append("HTF bullish alignment")
            elif htf_bias < 0 and score < 0:
                score -= 1.5; confidence += 7; reasons.append("HTF bearish alignment")
            if htf_sr_bias > 0 and score >= 0: score += 0.5
            elif htf_sr_bias < 0 and score <= 0: score -= 0.5

        confidence += min(abs(score) * 1.5, 10)
        confidence  = max(0, min(100, int(round(confidence))))
        score_int   = int(round(score))
        action      = self.determine_action(score_int, confidence, regime)

        return Signal(
            symbol=symbol, action=action, score=score_int, confidence=confidence,
            regime=regime, reason=", ".join(reasons) if reasons else "No edge",
            profile=profile, atr_value=atr_value, close_price=close_price,
            ema_fast=ema_fast, ema_slow=ema_slow, rsi_value=rsi_value,
            macd_hist=macd_hist, volume_ratio=volume_ratio,
            breakout_up=breakout_up, breakout_down=breakout_down,
            adx_value=adx_value, vwap_value=vwap_value,
            htf_bias=htf_bias, htf_sr_bias=htf_sr_bias,
        )

    # ------------------------------------------------------------------ #
    # NAS100 Asia Range model
    # ------------------------------------------------------------------ #

    def _preopen_drift_side(self, preopen_df, asia_high, asia_low, atr_value):
        if preopen_df.empty or len(preopen_df) < 4 or atr_value <= 0:
            return None
        first_open   = float(preopen_df.iloc[0]["open"])
        last_close   = float(preopen_df.iloc[-1]["close"])
        session_span = max(float(preopen_df["high"].max()) - float(preopen_df["low"].min()), 1e-9)
        body_ratio   = float(preopen_df["body"].mean() / preopen_df["range"].mean()) if float(preopen_df["range"].mean()) > 0 else 1.0
        drift_ratio  = abs(last_close - first_open) / session_span
        near_high    = abs(last_close - asia_high) <= atr_value * 0.45
        near_low     = abs(last_close - asia_low)  <= atr_value * 0.45
        if body_ratio > 0.62 or drift_ratio < 0.45:
            return None
        if last_close > first_open and near_high: return "up"
        if last_close < first_open and near_low:  return "down"
        return None

    def _detect_sweep(self, ltf, reference_time, asia_high, asia_low, atr_value, drift_side):
        open_df    = self._slice_window_ny(ltf, reference_time, self.cfg.nas100_open_window_ny)
        if open_df.empty: return None
        tolerance  = atr_value * self.cfg.asia_sweep_min_atr
        candidates = []
        for _, row in open_df.iterrows():
            later = ltf[ltf["time"] >= row["time"]]
            if float(row["high"]) >= asia_high + tolerance and (later["close"] < asia_high).any():
                candidates.append({"action": "short", "sweep_side": "buy_side",  "time": self._ensure_utc(row["time"]), "extreme": float(row["high"])})
            if float(row["low"])  <= asia_low  - tolerance and (later["close"] > asia_low).any():
                candidates.append({"action": "long",  "sweep_side": "sell_side", "time": self._ensure_utc(row["time"]), "extreme": float(row["low"])})
        if not candidates: return None
        expected = {"up": "short", "down": "long"}.get(drift_side) if drift_side else None
        if expected:
            preferred = [c for c in candidates if c["action"] == expected]
            if preferred: return max(preferred, key=lambda x: x["time"])
        return max(candidates, key=lambda x: x["time"])

    def _find_cisd_confirmation(self, post_sweep, action):
        for idx in range(2, len(post_sweep)):
            left    = post_sweep.iloc[idx - 2]
            middle  = post_sweep.iloc[idx - 1]
            current = post_sweep.iloc[idx]
            atr_v   = float(current["atr"]) if float(current["atr"]) > 0 else 0.0
            tol     = atr_v * self.cfg.fvg_eq_tolerance_atr
            if action == "short":
                displ      = float(current["open"]) - float(current["close"])
                cisd       = float(current["close"]) < float(middle["low"]) and displ >= atr_v * self.cfg.cisd_displacement_atr
                gap_exists = float(left["low"]) > float(current["high"])
                if not cisd or not gap_exists: continue
                eq    = (float(left["low"]) + float(current["high"])) / 2
                later = post_sweep.iloc[idx + 1:]
                if not later.empty and ((later["high"] >= eq - tol) & (later["close"] < eq)).any():
                    return {"cisd_time": self._ensure_utc(current["time"]), "eq": eq, "fvg_side": "bearish"}
            else:
                displ      = float(current["close"]) - float(current["open"])
                cisd       = float(current["close"]) > float(middle["high"]) and displ >= atr_v * self.cfg.cisd_displacement_atr
                gap_exists = float(left["high"]) < float(current["low"])
                if not cisd or not gap_exists: continue
                eq    = (float(left["high"]) + float(current["low"])) / 2
                later = post_sweep.iloc[idx + 1:]
                if not later.empty and ((later["low"] <= eq + tol) & (later["close"] > eq)).any():
                    return {"cisd_time": self._ensure_utc(current["time"]), "eq": eq, "fvg_side": "bullish"}
        return None

    def _analyze_nas100_asia_model(self, symbol, df, df_htf, df_ltf, base_signal):
        if not self.cfg.use_nas100_asia_model or not symbol.startswith("NAS100") or df_ltf is None or df_ltf.empty:
            return None
        ref = self._reference_time(df)
        if not (self._in_any_window_ny(ref, self.cfg.nas100_open_window_ny) or
                self._in_any_window_ny(ref, self.cfg.nas100_macro_windows_ny)):
            return None
        ltf = self._prep(df_ltf[df_ltf["time"] <= ref].copy())
        if len(ltf) < 60: return None
        asia_df    = self._slice_window_ny(ltf, ref, self.cfg.asia_range_ny)
        preopen_df = self._slice_window_ny(ltf, ref, self.cfg.nas100_preopen_window_ny)
        if asia_df.empty or len(asia_df) < 6: return None
        asia_high  = float(asia_df["high"].max())
        asia_low   = float(asia_df["low"].min())
        asia_width = asia_high - asia_low
        atr_value  = float(base_signal.atr_value) if float(base_signal.atr_value) > 0 else float(ltf.iloc[-1]["atr"])
        if atr_value <= 0 or asia_width <= 0 or asia_width > atr_value * self.cfg.asia_range_max_width_atr: return None
        if abs(float(asia_df.iloc[-1]["close"]) - float(asia_df.iloc[0]["open"])) / max(asia_width, 1e-9) > self.cfg.asia_range_max_drift_ratio: return None
        drift_side   = self._preopen_drift_side(preopen_df, asia_high, asia_low, atr_value)
        sweep        = self._detect_sweep(ltf, ref, asia_high, asia_low, atr_value, drift_side)
        if sweep is None: return None
        post_sweep   = ltf[ltf["time"] >= sweep["time"]].copy().reset_index(drop=True)
        confirmation = self._find_cisd_confirmation(post_sweep, sweep["action"])
        if confirmation is None: return None
        close_price  = float(df.iloc[-1]["close"])
        target_price = asia_low if sweep["action"] == "short" else asia_high
        if sweep["action"] == "short" and close_price <= target_price + atr_value * 0.15: return None
        if sweep["action"] == "long"  and close_price >= target_price - atr_value * 0.15: return None
        score       = max(self.cfg.mode_threshold() + 2, 5) * (-1 if sweep["action"] == "short" else 1)
        confidence  = max(base_signal.confidence, self.cfg.asia_model_confidence_floor) + 8 + 12 + 12
        if drift_side: confidence += 6
        if self._in_any_window_ny(ref, self.cfg.nas100_macro_windows_ny): confidence += 5
        if (sweep["action"] == "long" and base_signal.htf_bias > 0) or (sweep["action"] == "short" and base_signal.htf_bias < 0): confidence += 6
        if base_signal.regime == "volatile": confidence -= 6
        confidence = max(0, min(100, confidence))
        regime = "trend" if base_signal.regime != "volatile" else "volatile"
        action = self.determine_action(score, confidence, regime)
        if action == "hold": return None
        reasons = [
            "Asia range clean",
            f"Asia H:{asia_high:.2f} L:{asia_low:.2f}",
            f"Pre-open drift {drift_side or 'mixed'}",
            f"{sweep['sweep_side']} sweep at NY open",
            f"CISD + {confirmation['fvg_side']} FVG EQ",
            f"Target {'Asia Low' if sweep['action'] == 'short' else 'Asia High'}",
        ]
        if self._in_any_window_ny(ref, self.cfg.nas100_macro_windows_ny): reasons.append("Macro window active")
        if (sweep["action"] == "long" and base_signal.htf_bias > 0) or (sweep["action"] == "short" and base_signal.htf_bias < 0): reasons.append("HTF aligned")
        return Signal(
            symbol=symbol, action=action, score=score, confidence=int(confidence),
            regime=regime, reason=", ".join(reasons), profile=base_signal.profile,
            atr_value=atr_value, close_price=close_price,
            ema_fast=base_signal.ema_fast, ema_slow=base_signal.ema_slow,
            rsi_value=base_signal.rsi_value, macd_hist=base_signal.macd_hist,
            volume_ratio=base_signal.volume_ratio,
            breakout_up=base_signal.breakout_up, breakout_down=base_signal.breakout_down,
            adx_value=base_signal.adx_value, vwap_value=base_signal.vwap_value,
            htf_bias=base_signal.htf_bias, htf_sr_bias=base_signal.htf_sr_bias,
            model="nas100_asia_range", target_price=target_price,
            target_label="Asia Low" if sweep["action"] == "short" else "Asia High",
            sweep_side=sweep["sweep_side"], cisd_detected=True,
            asia_high=asia_high, asia_low=asia_low, first_fvg_side=confirmation["fvg_side"],
        )

    # ------------------------------------------------------------------ #
    # NEW: XAUT London Open Range (LOR) model
    # London 07:00-08:00 arası high/low belirlenir.
    # 08:00-09:30 arasında sweep + reclaim sinyali aranır.
    # ------------------------------------------------------------------ #

    def _analyze_xaut_london_model(self, symbol, df, df_htf, df_ltf, base_signal) -> Signal | None:
        if not symbol.startswith("XAUT") or df_ltf is None or df_ltf.empty:
            return None
        ref = self._reference_time(df)
        # Sadece London 08:00-09:30 penceresinde aktif
        if not self._in_any_window_london(ref, "08:00-09:30"):
            return None
        ltf = self._prep(df_ltf[df_ltf["time"] <= ref].copy())
        if len(ltf) < 30:
            return None
        lor_df = self._slice_window_london(ltf, ref, "07:00-08:00")
        if lor_df.empty or len(lor_df) < 3:
            return None
        lor_high  = float(lor_df["high"].max())
        lor_low   = float(lor_df["low"].min())
        lor_width = lor_high - lor_low
        atr_value = float(base_signal.atr_value) if float(base_signal.atr_value) > 0 else float(ltf.iloc[-1]["atr"])
        if atr_value <= 0 or lor_width < atr_value * 0.3 or lor_width > atr_value * 5.0:
            return None
        post_lor = ltf[ltf["time"] > lor_df.iloc[-1]["time"]].copy()
        if post_lor.empty:
            return None
        close_price  = float(df.iloc[-1]["close"])
        sweep_tol    = atr_value * 0.15
        sweep_low    = (post_lor["low"]  < lor_low  - sweep_tol).any()
        sweep_high   = (post_lor["high"] > lor_high + sweep_tol).any()
        action = sweep_side = target_price = target_label = None
        if sweep_low and lor_low < close_price < lor_high + atr_value * 0.3:
            action, sweep_side, target_price, target_label = "long",  "sell_side", lor_high, "LOR High"
        elif sweep_high and lor_low - atr_value * 0.3 < close_price < lor_high:
            action, sweep_side, target_price, target_label = "short", "buy_side",  lor_low,  "LOR Low"
        if action is None:
            return None
        # HTF alignment
        if action == "long"  and base_signal.htf_bias < 0: return None
        if action == "short" and base_signal.htf_bias > 0: return None
        score      = self.cfg.mode_threshold() + 2
        if action == "short": score *= -1
        confidence = max(base_signal.confidence, 55) + 10
        if base_signal.regime == "trend":    confidence += 5
        elif base_signal.regime == "volatile": confidence -= 5
        if (action == "long" and base_signal.htf_bias > 0) or (action == "short" and base_signal.htf_bias < 0):
            confidence += 7
        if base_signal.rsi_value > 55 and action == "long":  confidence += 3
        if base_signal.rsi_value < 45 and action == "short": confidence += 3
        confidence = max(0, min(100, confidence))
        final_action = self.determine_action(score, confidence, base_signal.regime)
        if final_action == "hold": return None
        reasons = [
            "XAUT London Open Range",
            f"LOR H:{lor_high:.2f} L:{lor_low:.2f}",
            f"{sweep_side} sweep + reclaim",
            f"Target {target_label}",
            f"Regime {base_signal.regime}",
        ]
        if (action == "long" and base_signal.htf_bias > 0) or (action == "short" and base_signal.htf_bias < 0):
            reasons.append("HTF aligned")
        return Signal(
            symbol=symbol, action=final_action, score=score, confidence=int(confidence),
            regime=base_signal.regime, reason=", ".join(reasons), profile=base_signal.profile,
            atr_value=atr_value, close_price=close_price,
            ema_fast=base_signal.ema_fast, ema_slow=base_signal.ema_slow,
            rsi_value=base_signal.rsi_value, macd_hist=base_signal.macd_hist,
            volume_ratio=base_signal.volume_ratio,
            breakout_up=base_signal.breakout_up, breakout_down=base_signal.breakout_down,
            adx_value=base_signal.adx_value, vwap_value=base_signal.vwap_value,
            htf_bias=base_signal.htf_bias, htf_sr_bias=base_signal.htf_sr_bias,
            model="xaut_london_open_range",
            target_price=target_price, target_label=target_label, sweep_side=sweep_side,
            asia_high=lor_high, asia_low=lor_low,
        )

    # ------------------------------------------------------------------ #
    # Main entry — FIX: df_ltf parametresi eklendi
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        df_ltf: pd.DataFrame | None = None,   # <-- BU EKSİKTİ, scanner crash yapıyordu
    ) -> Signal:
        base_signal = self._analyze_base(symbol, df, df_htf)

        # NAS100: Asia Range + CISD modeli
        nas_signal = self._analyze_nas100_asia_model(symbol, df, df_htf, df_ltf, base_signal)
        if nas_signal is not None:
            return nas_signal

        # XAUT: London Open Range modeli (YENİ)
        lor_signal = self._analyze_xaut_london_model(symbol, df, df_htf, df_ltf, base_signal)
        if lor_signal is not None:
            return lor_signal

        return base_signal
