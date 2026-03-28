from dataclasses import dataclass
from config import BotConfig

@dataclass
class AdaptiveLimits:
    regime: str
    atr_pct: float
    risk_per_trade: float
    leverage: int
    max_spread_pct: float
    max_trades_per_day: int
    cooldown_minutes: int
    atr_stop_mult: float
    trading_allowed: bool


def compute_atr_pct(atr_value: float, close_price: float) -> float:
    if close_price <= 0:
        return 0.0
    return atr_value / close_price


class DynamicLimitManager:
    def __init__(self, config: BotConfig):
        self.config = config

    def detect_regime(self, atr_pct: float) -> str:
        if atr_pct <= self.config.vol_regime_low_atr_pct:
            return "low"
        elif atr_pct <= self.config.vol_regime_medium_atr_pct:
            return "medium"
        elif atr_pct <= self.config.vol_regime_high_atr_pct:
            return "high"
        return "extreme"

    def _pick_multiplier(self, regime: str, prefix: str) -> float:
        mapping = {
            "low": getattr(self.config, f"{prefix}_low_vol"),
            "medium": getattr(self.config, f"{prefix}_medium_vol"),
            "high": getattr(self.config, f"{prefix}_high_vol"),
            "extreme": getattr(self.config, f"{prefix}_extreme_vol"),
        }
        return mapping[regime]

    def get_limits(self, atr_pct: float) -> AdaptiveLimits:
        if not getattr(self.config, "dynamic_limits_enabled", False):
            return AdaptiveLimits(
                regime="static",
                atr_pct=atr_pct,
                risk_per_trade=self.config.risk_per_trade,
                leverage=self.config.leverage,
                max_spread_pct=self.config.max_spread_pct,
                max_trades_per_day=self.config.max_trades_per_day,
                cooldown_minutes=self.config.cooldown_minutes,
                atr_stop_mult=self.config.atr_stop_mult,
                trading_allowed=True,
            )

        regime = self.detect_regime(atr_pct)

        risk_mult = self._pick_multiplier(regime, "risk_mult")
        lev_mult = self._pick_multiplier(regime, "leverage_mult")
        spread_mult = self._pick_multiplier(regime, "spread_mult")
        trades_mult = self._pick_multiplier(regime, "trades_per_day_mult")
        cooldown_mult = self._pick_multiplier(regime, "cooldown_mult")
        stop_mult = self._pick_multiplier(regime, "stop_mult")

        trading_allowed = not (
            regime == "extreme" and self.config.disable_trading_extreme_vol
        )

        return AdaptiveLimits(
            regime=regime,
            atr_pct=atr_pct,
            risk_per_trade=self.config.risk_per_trade * risk_mult,
            leverage=max(1, round(self.config.leverage * lev_mult)),
            max_spread_pct=self.config.max_spread_pct * spread_mult,
            max_trades_per_day=max(1, round(self.config.max_trades_per_day * trades_mult)),
            cooldown_minutes=max(1, round(self.config.cooldown_minutes * cooldown_mult)),
            atr_stop_mult=self.config.atr_stop_mult * stop_mult,
            trading_allowed=trading_allowed,
        )
