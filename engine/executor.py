from __future__ import annotations

from datetime import datetime, timezone

from engine.paper_wallet import Position


class Executor:
    def __init__(self, config, wallet):
        self.cfg = config
        self.wallet = wallet

    def open_position(self, symbol: str, side: str, entry_price: float, risk_plan, reason: str, regime: str, score: int) -> dict:
        effective_entry = entry_price + (entry_price * self.cfg.slippage_rate) if side == "long" else entry_price - (entry_price * self.cfg.slippage_rate)
        fees = abs(risk_plan.notional) * self.cfg.fee_rate
        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=round(effective_entry, 6),
            quantity=round(risk_plan.quantity, 6),
            leverage=self.cfg.leverage,
            stop_loss=round(risk_plan.stop_loss, 6),
            take_profit=round(risk_plan.take_profit, 6),
            trailing_active=False,
            trailing_activation_price=round(risk_plan.trailing_activation_price, 6),
            trailing_gap_pct=self.cfg.trailing_gap_pct,
            trailing_stop=None,
            partial_take_profit=round(risk_plan.partial_take_profit, 6),
            partial_close_ratio=risk_plan.partial_close_ratio,
            partial_taken=False,
            break_even_trigger=round(risk_plan.break_even_trigger, 6),
            break_even_done=False,
            opened_at=datetime.now(timezone.utc).isoformat(),
            highest_price=round(effective_entry, 6),
            lowest_price=round(effective_entry, 6),
            fees_paid=round(fees, 6),
            reason=reason,
            regime=regime,
            score=score,
        )
        self.wallet.open_trade(pos, risk_plan.margin_used)
        return self.wallet.open_position
