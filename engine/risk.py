from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.dynamic_limits import AdaptiveLimits


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

    # KURUMSAL RISK METADATA
    blocked: bool = False
    blocked_reason: str = ""
    breakdown: dict = field(default_factory=dict)


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

    def get_drawdown_multiplier(self, wallet) -> tuple[float, str]:
        balance = wallet.balance
        peak = float(wallet.data.get("peak_equity", self.cfg.starting_balance))
        dd = (peak - balance) / peak if peak > 0 else 0
        cfg = self.cfg.drawdown
        
        if dd >= cfg.max_drawdown_pct:
            return 0.0, f"Max drawdown aşıldı ({dd:.1%})"
        if dd >= cfg.tier2_drawdown_pct:
            return cfg.tier2_size_multiplier, f"Tier-2 drawdown ({dd:.1%})"
        if dd >= cfg.tier1_drawdown_pct:
            return cfg.tier1_size_multiplier, f"Tier-1 drawdown ({dd:.1%})"
        return 1.0, f"Drawdown ({dd:.1%})"

    def calculate_kelly(self, wallet, base_risk: float) -> tuple[float, str]:
        cfg = self.cfg.kelly
        if not cfg.enabled:
            return base_risk, "Sabit Risk"
            
        stats = wallet.performance_summary()
        trades = stats.get("trades", 0)
        
        if trades < cfg.min_trades_for_calculation:
            return base_risk, f"Kelly bekliyor ({trades}/{cfg.min_trades_for_calculation})"
            
        wins = stats.get("wins", 0)
        win_rate = wins / trades if trades > 0 else 0
        avg_win = stats.get("avg_win", 0)
        avg_loss = abs(stats.get("avg_loss", 0))
        
        if avg_loss == 0 or wins == 0:
            return base_risk, "Sabit Risk (Yetersiz Data)"
            
        payoff_ratio = avg_win / avg_loss
        kelly = win_rate - ((1 - win_rate) / payoff_ratio)
        
        if kelly <= 0:
            return cfg.min_kelly_pct, f"Sistem kaybediyor (Kelly_min {cfg.min_kelly_pct*100:.2f}%)"
            
        adjusted = max(cfg.min_kelly_pct, min(kelly * cfg.fraction, cfg.max_kelly_pct))
        return adjusted, f"Kelly ({adjusted*100:.2f}%)"

    def get_equity_curve_multiplier(self, wallet) -> tuple[float, str]:
        cfg = self.cfg.equity_curve
        if not cfg.enabled:
            return 1.0, "Equity Curve Kapalı"
            
        history = wallet.data.get("equity_history", [self.cfg.starting_balance])
        if len(history) < cfg.ema_period:
            return 1.0, f"Equity EMA bekliyor ({len(history)}/{cfg.ema_period})"
            
        k = 2 / (cfg.ema_period + 1)
        ema = history[0]
        for val in history[1:]:
            ema = val * k + ema * (1 - k)
            
        current = wallet.balance
        distance_pct = (current - ema) / ema if ema > 0 else 0
        
        if distance_pct < -cfg.hard_stop_below_ema_pct:
            return 0.0, f"Equity, EMA'nın %{abs(distance_pct)*100:.1f} altında. Durduruldu."
        if current < ema:
            return cfg.below_ema_multiplier, f"EMA altında (x{cfg.below_ema_multiplier})"
            
        return cfg.above_ema_bonus, "EMA üstünde"

    def check_portfolio_heat(self, wallet, new_risk_usdt: float) -> tuple[bool, str]:
        cfg = self.cfg.portfolio_heat
        balance = wallet.balance
        current_heat = 0
        if wallet.open_position:
            entry = float(wallet.open_position["entry_price"])
            sl = float(wallet.open_position["stop_loss"])
            qty = float(wallet.open_position["quantity"])
            current_heat = abs(entry - sl) * qty
            
        new_heat_pct = (current_heat + new_risk_usdt) / balance if balance > 0 else 0
        if new_heat_pct > cfg.max_portfolio_heat_pct:
            return False, f"Portfolio Heat Aşıldı: %{new_heat_pct*100:.1f} > %{cfg.max_portfolio_heat_pct*100:.1f}"
        return True, f"Heat: %{new_heat_pct*100:.1f}"

    def check_profit_protection(self, wallet) -> tuple[bool, str]:
        cfg = self.cfg.profit_protection
        if not cfg.enabled:
            return True, ""
            
        balance = wallet.balance
        starting = self.cfg.starting_balance
        peak = float(wallet.data.get("peak_equity", starting))
        
        profit = peak - starting
        profit_pct = profit / starting if starting > 0 else 0
        
        if profit_pct < cfg.min_profit_to_activate_pct:
            return True, "Kilit inaktif"
            
        locked_amount = starting + (profit * cfg.profit_lock_ratio)
        if balance < locked_amount:
            return False, f"Kilitli Kâr Korunuyor (Bakiye: {balance:.2f} < Kilit: {locked_amount:.2f})"
        return True, f"Kilit Aktif: {locked_amount:.2f}"

    def get_dynamic_leverage(self, regime: str, base_limit: int, wallet) -> int:
        cfg = self.cfg.dynamic_leverage
        if not cfg.enabled:
            return base_limit
            
        max_lev = base_limit
        if "low" in regime or "trend" in regime:
            max_lev = cfg.calm_max_leverage
        elif "high" in regime or "volatile" in regime:
            max_lev = cfg.volatile_max_leverage
        elif "extreme" in regime:
            max_lev = cfg.crisis_max_leverage
        else:
            max_lev = cfg.normal_max_leverage
            
        if cfg.drawdown_leverage_reduction:
            balance = wallet.balance
            peak = float(wallet.data.get("peak_equity", self.cfg.starting_balance))
            dd = (peak - balance) / peak if peak > 0 else 0
            if dd > 0.10:
                max_lev = max(1, max_lev // 2)
            elif dd > 0.05:
                max_lev = max(1, int(max_lev * 0.7))
                
        return min(base_limit, max_lev)

    def build_plan(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr_value: float,
        wallet,
        regime: str,
        limits: AdaptiveLimits,
        confidence: int = 60,
    ) -> RiskPlan:
        # Create an empty template to return if blocked
        empty_plan = RiskPlan(
            side=side, entry_price=entry_price, stop_loss=0, take_profit=0,
            trailing_activation_price=0, trailing_gap_pct=0, quantity=0, margin_used=0,
            notional=0, estimated_fee=0, risk_distance=0, partial_take_profit=0,
            partial_close_ratio=0, break_even_trigger=0, confidence=confidence, regime=regime
        )

        wallet_balance = wallet.balance
        mode_risk = limits.risk_per_trade if self.cfg.risk_mode == "aggressive" else max(0.0125, limits.risk_per_trade * 0.6)
        
        # 1. Kâr Koruma Kontrolü
        profit_ok, profit_msg = self.check_profit_protection(wallet)
        if not profit_ok:
            empty_plan.blocked = True
            empty_plan.blocked_reason = profit_msg
            return empty_plan
            
        # 2. Drawdown Çarpanı
        dd_mult, dd_msg = self.get_drawdown_multiplier(wallet)
        if dd_mult <= 0:
            empty_plan.blocked = True
            empty_plan.blocked_reason = dd_msg
            return empty_plan
            
        # 3. Equity Curve Çarpanı
        eq_mult, eq_msg = self.get_equity_curve_multiplier(wallet)
        if eq_mult <= 0:
            empty_plan.blocked = True
            empty_plan.blocked_reason = eq_msg
            return empty_plan
            
        # 4. Kelly Criterion
        base_risk_pct, kelly_msg = self.calculate_kelly(wallet, mode_risk)
        
        # Diğer Çarpanlar
        symbol_mult = self.symbol_risk_multiplier(symbol)
        regime_mult = self.regime_risk_multiplier(regime)
        conf_mult = self.confidence_size_multiplier(confidence)
        
        final_risk_pct = base_risk_pct * dd_mult * eq_mult * symbol_mult * regime_mult * conf_mult
        risk_amount = wallet_balance * final_risk_pct
        
        # 5. Portfolio Heat Kontrolü
        heat_ok, heat_msg = self.check_portfolio_heat(wallet, risk_amount)
        if not heat_ok:
            empty_plan.blocked = True
            empty_plan.blocked_reason = heat_msg
            return empty_plan

        # Stop ve Mesafe Hesaplama
        base_stop_mult = limits.atr_stop_mult if self.cfg.risk_mode == "aggressive" else limits.atr_stop_mult * 1.12
        stop_mult = base_stop_mult * self.regime_stop_multiplier(regime)
        stop_distance = max(atr_value * stop_mult, entry_price * self.cfg.min_stop_distance_pct)
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

        # 6. Dinamik Kaldıraç
        active_leverage = self.get_dynamic_leverage(regime, limits.leverage, wallet)

        qty = risk_amount / stop_distance if stop_distance > 0 else 0.0
        notional = qty * entry_price
        margin_used = notional / active_leverage if active_leverage else notional
        estimated_fee = notional * (self.cfg.fee_rate + (self.cfg.slippage_rate * 2))

        if margin_used > wallet_balance * 0.95 and margin_used > 0:
            scale = (wallet_balance * 0.95) / margin_used
            qty *= scale
            notional = qty * entry_price
            margin_used = notional / active_leverage if active_leverage else notional
            estimated_fee = notional * (self.cfg.fee_rate + (self.cfg.slippage_rate * 2))

        partial_targets = [
            {"label": "tp1", "price": round(partial_tp, 6), "close_ratio": float(self.cfg.partial_close_ratio), "hit": False},
            {"label": "tp2", "price": round(second_partial_tp, 6), "close_ratio": float(self.cfg.secondary_partial_close_ratio), "hit": False},
        ]
        
        breakdown = {
            "Kelly_Base": f"{kelly_msg}",
            "Drawdown": f"x{dd_mult} ({dd_msg})",
            "Equity_Curve": f"x{eq_mult} ({eq_msg})",
            "Heat": heat_msg,
            "Profit_Lock": profit_msg,
            "Active_Leverage": f"{active_leverage}x"
        }

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
            blocked=False,
            blocked_reason="",
            breakdown=breakdown
        )
