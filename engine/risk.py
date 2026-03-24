from __future__ import annotations

from dataclasses import dataclass


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


class RiskManager:
    def __init__(self, config):
        self.cfg = config

    def daily_loss_breached(self, wallet) -> bool:
        return wallet.data["daily_realized_pnl"] <= -(self.cfg.starting_balance * self.cfg.daily_loss_limit_pct)

    def consecutive_losses_breached(self, wallet) -> bool:
        return wallet.data["consecutive_losses"] >= self.cfg.max_consecutive_losses

    def symbol_risk_multiplier(self, symbol: str) -> float:
        if symbol.startswith("NAS100"):
            return 0.75 if self.cfg.risk_mode == 'calm' else 0.9
        if symbol.startswith("XAUT"):
            return 0.8 if self.cfg.risk_mode == 'calm' else 1.0
        return 1.0

    def regime_risk_multiplier(self, regime: str) -> float:
        if regime == "trend":
            return 1.0 if self.cfg.risk_mode == 'calm' else 1.15
        if regime == "volatile":
            return 0.6 if self.cfg.risk_mode == 'calm' else 0.8
        return 0.75 if self.cfg.risk_mode == 'calm' else 0.95

    def build_plan(self, symbol: str, side: str, entry_price: float, atr_value: float, wallet_balance: float, regime: str) -> RiskPlan:
        mult = self.symbol_risk_multiplier(symbol) * self.regime_risk_multiplier(regime)
        mode_risk = self.cfg.risk_per_trade if self.cfg.risk_mode == 'aggressive' else max(0.0125, self.cfg.risk_per_trade * 0.6)
        risk_amount = wallet_balance * mode_risk * mult
        stop_mult = self.cfg.atr_stop_mult if self.cfg.risk_mode == 'aggressive' else self.cfg.atr_stop_mult * 1.15
        rr_ratio = self.cfg.rr_ratio if self.cfg.risk_mode == 'aggressive' else max(2.0, self.cfg.rr_ratio)
        stop_distance = max(atr_value * stop_mult, entry_price * 0.003)

        if side == "long":
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + (stop_distance * rr_ratio)
            trailing_activation = entry_price + (stop_distance * self.cfg.trailing_activation_r)
            partial_tp = entry_price + (stop_distance * self.cfg.partial_tp_r)
            break_even_trigger = entry_price + (stop_distance * self.cfg.break_even_r)
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - (stop_distance * rr_ratio)
            trailing_activation = entry_price - (stop_distance * self.cfg.trailing_activation_r)
            partial_tp = entry_price - (stop_distance * self.cfg.partial_tp_r)
            break_even_trigger = entry_price - (stop_distance * self.cfg.break_even_r)

        qty = risk_amount / stop_distance
        notional = qty * entry_price
        margin_used = notional / self.cfg.leverage
        estimated_fee = notional * self.cfg.fee_rate

        if margin_used > wallet_balance * 0.95:
            scale = (wallet_balance * 0.95) / margin_used
            qty *= scale
            notional = qty * entry_price
            margin_used = notional / self.cfg.leverage
            estimated_fee = notional * self.cfg.fee_rate

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
        )
