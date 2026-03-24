from __future__ import annotations

from datetime import datetime, timezone


class PositionManager:
    def __init__(self, config, wallet):
        self.cfg = config
        self.wallet = wallet

    def mark_equity(self, last_price: float) -> float:
        pos = self.wallet.open_position
        if pos is None:
            self.wallet.set_equity(self.wallet.balance)
            return self.wallet.balance
        qty = float(pos["quantity"])
        entry = float(pos["entry_price"])
        side = pos["side"]
        unrealized = (last_price - entry) * qty if side == "long" else (entry - last_price) * qty
        equity = self.wallet.balance + float(pos["margin_used"]) + unrealized
        self.wallet.set_equity(equity)
        return equity

    def update_and_check_exit(self, last_price: float, fresh_signal_action: str | None = None):
        pos = self.wallet.open_position
        if pos is None:
            return {"exit": False, "reason": None, "partial": None, "be": False}
        side = pos["side"]
        pos["highest_price"] = max(float(pos["highest_price"]), last_price)
        pos["lowest_price"] = min(float(pos["lowest_price"]), last_price)
        partial_info = None
        break_even = False

        # partial tp
        if not pos.get("partial_taken", False):
            if side == "long" and last_price >= float(pos["partial_take_profit"]):
                partial_info = self.wallet.partial_close(last_price, self.cfg.fee_rate, self.cfg.slippage_rate)
                pos = self.wallet.open_position
            elif side == "short" and last_price <= float(pos["partial_take_profit"]):
                partial_info = self.wallet.partial_close(last_price, self.cfg.fee_rate, self.cfg.slippage_rate)
                pos = self.wallet.open_position

        # break-even
        if pos is not None and not pos.get("break_even_done", False):
            if side == "long" and last_price >= float(pos["break_even_trigger"]):
                pos["stop_loss"] = max(float(pos["stop_loss"]), float(pos["entry_price"]))
                pos["break_even_done"] = True
                break_even = True
            elif side == "short" and last_price <= float(pos["break_even_trigger"]):
                pos["stop_loss"] = min(float(pos["stop_loss"]), float(pos["entry_price"]))
                pos["break_even_done"] = True
                break_even = True

        if pos is None:
            return {"exit": False, "reason": None, "partial": partial_info, "be": break_even}

        # trailing
        if not pos["trailing_active"]:
            if side == "long" and last_price >= float(pos["trailing_activation_price"]):
                pos["trailing_active"] = True
                pos["trailing_stop"] = last_price * (1 - float(pos["trailing_gap_pct"]))
            elif side == "short" and last_price <= float(pos["trailing_activation_price"]):
                pos["trailing_active"] = True
                pos["trailing_stop"] = last_price * (1 + float(pos["trailing_gap_pct"]))
        else:
            if side == "long":
                new_stop = float(pos["highest_price"]) * (1 - float(pos["trailing_gap_pct"]))
                pos["trailing_stop"] = max(float(pos["trailing_stop"]), new_stop)
            else:
                new_stop = float(pos["lowest_price"]) * (1 + float(pos["trailing_gap_pct"]))
                pos["trailing_stop"] = min(float(pos["trailing_stop"]), new_stop)

        # time stop
        opened_at = datetime.fromisoformat(pos["opened_at"])
        elapsed_minutes = (datetime.now(timezone.utc) - opened_at).total_seconds() / 60
        if elapsed_minutes >= self.cfg.time_stop_minutes:
            self.wallet.update_open_position(pos)
            return {"exit": True, "reason": "time_stop", "partial": partial_info, "be": break_even}

        # opposite signal exit
        if fresh_signal_action and ((side == "long" and fresh_signal_action == "short") or (side == "short" and fresh_signal_action == "long")):
            self.wallet.update_open_position(pos)
            return {"exit": True, "reason": "opposite_signal", "partial": partial_info, "be": break_even}

        self.wallet.update_open_position(pos)

        if side == "long":
            if last_price <= float(pos["stop_loss"]):
                return {"exit": True, "reason": "stop_loss", "partial": partial_info, "be": break_even}
            if last_price >= float(pos["take_profit"]):
                return {"exit": True, "reason": "take_profit", "partial": partial_info, "be": break_even}
            if pos["trailing_active"] and last_price <= float(pos["trailing_stop"]):
                return {"exit": True, "reason": "trailing_stop", "partial": partial_info, "be": break_even}
        else:
            if last_price >= float(pos["stop_loss"]):
                return {"exit": True, "reason": "stop_loss", "partial": partial_info, "be": break_even}
            if last_price <= float(pos["take_profit"]):
                return {"exit": True, "reason": "take_profit", "partial": partial_info, "be": break_even}
            if pos["trailing_active"] and last_price >= float(pos["trailing_stop"]):
                return {"exit": True, "reason": "trailing_stop", "partial": partial_info, "be": break_even}
        return {"exit": False, "reason": None, "partial": partial_info, "be": break_even}
