from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskPlan:
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    trailing_activation_price: float
    trailing_gap_pct: float
    quantity: float
    margin_used: float
    notional: float
    estimated_fee: float
    risk_distance: float
    partial_take_profit: float
    partial_close_ratio: float
    break_even_trigger: float
    confidence: int
    regime: str
    partial_targets: list[dict[str, Any]] = field(default_factory=list)


class RiskManager:
    def __init__(self, config):
        self.cfg = config

    def daily_loss_breached(self, wallet) -> bool:
        return wallet.data["daily_realized_pnl"] <= -(self.cfg.starting_balance * self.cfg.daily_loss_limit_pct)

    def consecutive_losses_breached(self, wallet) -> bool:
        return wallet.data["consecutive_losses"] >= self.cfg.max_consecutive_losses

    def symbol_risk_multiplier(self, symbol: str) -> float:
        if symbol.startswith("NAS100"):
            return 0.8 if self.cfg.risk_mode == "calm" else 0.95
        if symbol.startswith("XAUT"):
            return 0.9 if self.cfg.risk_mode == "calm" else 1.0
        return 1.0

    def regime_risk_multiplier(self, regime: str) -> float:
        if regime == "trend":
            return 1.0 if self.cfg.risk_mode == "calm" else 1.1
        if regime == "volatile":
            return 0.65 if self.cfg.risk_mode == "calm" else 0.8
        return 0.8 if self.cfg.risk_mode == "calm" else 0.95

    def regime_stop_multiplier(self, regime: str) -> float:
        if regime == "trend":
            return 0.95
        if regime == "volatile":
            return 1.3
        return 1.1

    def confidence_size_multiplier(self, confidence: int) -> float:
        if confidence >= self.cfg.confidence_size_boost_threshold:
            return self.cfg.confidence_size_boost_multiplier
        if confidence < self.cfg.confidence_size_reduce_threshold:
            return self.cfg.confidence_size_reduce_multiplier
        if confidence < self.cfg.mode_confidence_min():
            return 0.85
        return 1.0

    def regime_rr_ratio(self, regime: str, confidence: int) -> float:
        base_rr = self.cfg.rr_ratio
        if regime == "trend":
            base_rr += 0.2
        elif regime == "range":
            base_rr -= 0.1
        if confidence >= 80:
            base_rr += 0.1
        return max(base_rr, self.cfg.partial_tp_r + 0.7)

    def build_plan(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr_value: float,
        wallet_balance: float,
        regime: str,
        confidence: int = 60,
    ) -> RiskPlan:
        mult = self.symbol_risk_multiplier(symbol) * self.regime_risk_multiplier(regime)
        mult *= self.confidence_size_multiplier(confidence)

        mode_risk = self.cfg.risk_per_trade if self.cfg.risk_mode == "aggressive" else max(0.0125, self.cfg.risk_per_trade * 0.6)
        risk_amount = wallet_balance * mode_risk * mult

        base_stop_mult = self.cfg.atr_stop_mult if self.cfg.risk_mode == "aggressive" else self.cfg.atr_stop_mult * 1.12
        stop_mult = base_stop_mult * self.regime_stop_multiplier(regime)
        stop_distance = max(atr_value * stop_mult, entry_price * 0.0032)
        rr_ratio = self.regime_rr_ratio(regime, confidence)

        if side == "long":
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + (stop_distance * rr_ratio)
            trailing_activation = entry_price + (stop_distance * self.cfg.trailing_activation_r)
            partial_tp = entry_price + (stop_distance * self.cfg.partial_tp_r)
            second_partial_tp = entry_price + (stop_distance * min(self.cfg.secondary_partial_tp_r, rr_ratio - 0.15))
            break_even_trigger = entry_price + (stop_distance * self.cfg.break_even_r)
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - (stop_distance * rr_ratio)
            trailing_activation = entry_price - (stop_distance * self.cfg.trailing_activation_r)
            partial_tp = entry_price - (stop_distance * self.cfg.partial_tp_r)
            second_partial_tp = entry_price - (stop_distance * min(self.cfg.secondary_partial_tp_r, rr_ratio - 0.15))
            break_even_trigger = entry_price - (stop_distance * self.cfg.break_even_r)

        qty = risk_amount / stop_distance if stop_distance > 0 else 0.0
        notional = qty * entry_price
        margin_used = notional / self.cfg.leverage if self.cfg.leverage else notional
        estimated_fee = notional * (self.cfg.fee_rate + (self.cfg.slippage_rate * 2))

        if margin_used > wallet_balance * 0.95 and margin_used > 0:
            scale = (wallet_balance * 0.95) / margin_used
            qty *= scale
            notional = qty * entry_price
            margin_used = notional / self.cfg.leverage if self.cfg.leverage else notional
            estimated_fee = notional * (self.cfg.fee_rate + (self.cfg.slippage_rate * 2))

        partial_targets = [
            {
                "label": "tp1",
                "price": round(partial_tp, 6),
                "close_ratio": float(self.cfg.partial_close_ratio),
                "hit": False,
            },
            {
                "label": "tp2",
                "price": round(second_partial_tp, 6),
                "close_ratio": float(self.cfg.secondary_partial_close_ratio),
                "hit": False,
            },
        ]

        return RiskPlan(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_activation_price=trailing_activation,
            trailing_gap_pct=self.cfg.trailing_gap_pct,
            quantity=qty,
            margin_used=margin_used,
            notional=notional,
            estimated_fee=estimated_fee,
            risk_distance=stop_distance,
            partial_take_profit=partial_tp,
            partial_close_ratio=self.cfg.partial_close_ratio,
            break_even_trigger=break_even_trigger,
            confidence=confidence,
            regime=regime,
            partial_targets=partial_targets,
        )
