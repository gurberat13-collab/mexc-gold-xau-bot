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

    def _is_profitable(self, pos: dict, last_price: float) -> bool:
        entry = float(pos["entry_price"])
        if pos["side"] == "long":
            return last_price > entry
        return last_price < entry

    def _ensure_partial_targets(self, pos: dict) -> list[dict]:
        targets = pos.get("partial_targets")
        if isinstance(targets, list) and targets:
            return targets
        secondary_price = float(pos["partial_take_profit"])
        take_profit = float(pos["take_profit"])
        if pos["side"] == "long":
            secondary_price = float(pos["partial_take_profit"]) + ((take_profit - float(pos["partial_take_profit"])) * 0.55)
        else:
            secondary_price = float(pos["partial_take_profit"]) - ((float(pos["partial_take_profit"]) - take_profit) * 0.55)
        targets = [
            {
                "label": "tp1",
                "price": float(pos["partial_take_profit"]),
                "close_ratio": float(pos.get("partial_close_ratio", 0.35)),
                "hit": False,
            },
            {
                "label": "tp2",
                "price": secondary_price,
                "close_ratio": float(self.cfg.secondary_partial_close_ratio),
                "hit": False,
            },
        ]
        pos["partial_targets"] = targets
        return targets

    def _process_partial_targets(self, pos: dict, last_price: float) -> list[dict]:
        partials: list[dict] = []
        targets = self._ensure_partial_targets(pos)
        for target in targets:
            if target.get("hit"):
                continue
            hit = last_price >= float(target["price"]) if pos["side"] == "long" else last_price <= float(target["price"])
            if not hit:
                continue
            partial_info = self.wallet.partial_close(
                float(target["price"]),
                self.cfg.fee_rate,
                self.cfg.slippage_rate,
                close_ratio=float(target["close_ratio"]),
                label=str(target["label"]),
            )
            if partial_info:
                partials.append(partial_info)
            pos = self.wallet.open_position
            if pos is None:
                break
        return partials

    def update_and_check_exit(
        self,
        last_price: float,
        fresh_signal_action: str | None = None,
        fresh_signal_confidence: int | None = None,
    ):
        pos = self.wallet.open_position
        if pos is None:
            return {"exit": False, "reason": None, "partial": None, "partials": [], "be": False}

        side = pos["side"]
        pos["highest_price"] = max(float(pos.get("highest_price", last_price)), last_price)
        pos["lowest_price"] = min(float(pos.get("lowest_price", last_price)), last_price)
        pos.setdefault("initial_quantity", pos["quantity"])
        partials = self._process_partial_targets(pos, last_price)
        pos = self.wallet.open_position
        break_even = False

        if pos is None:
            return {"exit": False, "reason": None, "partial": partials[0] if partials else None, "partials": partials, "be": break_even}

        if pos is not None and not pos.get("break_even_done", False):
            if side == "long" and last_price >= float(pos["break_even_trigger"]):
                pos["stop_loss"] = max(float(pos["stop_loss"]), float(pos["entry_price"]))
                pos["break_even_done"] = True
                break_even = True
            elif side == "short" and last_price <= float(pos["break_even_trigger"]):
                pos["stop_loss"] = min(float(pos["stop_loss"]), float(pos["entry_price"]))
                pos["break_even_done"] = True
                break_even = True

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

        opened_at = datetime.fromisoformat(pos["opened_at"])
        elapsed_minutes = (datetime.now(timezone.utc) - opened_at).total_seconds() / 60
        effective_time_stop = float(self.cfg.time_stop_minutes)
        if self._is_profitable(pos, last_price):
            effective_time_stop *= float(self.cfg.profitable_time_stop_extension)
        if elapsed_minutes >= effective_time_stop:
            self.wallet.update_open_position(pos)
            return {"exit": True, "reason": "time_stop", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}

        opposite_signal = fresh_signal_action and ((side == "long" and fresh_signal_action == "short") or (side == "short" and fresh_signal_action == "long"))
        if opposite_signal and (fresh_signal_confidence or 0) >= self.cfg.opposite_signal_confidence_min and self._is_profitable(pos, last_price):
            self.wallet.update_open_position(pos)
            return {
                "exit": True,
                "reason": "opposite_signal",
                "partial": partials[0] if partials else None,
                "partials": partials,
                "be": break_even,
            }

        self.wallet.update_open_position(pos)

        if side == "long":
            if last_price <= float(pos["stop_loss"]):
                return {"exit": True, "reason": "stop_loss", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
            if last_price >= float(pos["take_profit"]):
                return {"exit": True, "reason": "take_profit", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
            if pos["trailing_active"] and last_price <= float(pos["trailing_stop"]):
                return {"exit": True, "reason": "trailing_stop", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
        else:
            if last_price >= float(pos["stop_loss"]):
                return {"exit": True, "reason": "stop_loss", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
            if last_price <= float(pos["take_profit"]):
                return {"exit": True, "reason": "take_profit", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
            if pos["trailing_active"] and last_price >= float(pos["trailing_stop"]):
                return {"exit": True, "reason": "trailing_stop", "partial": partials[0] if partials else None, "partials": partials, "be": break_even}

        return {"exit": False, "reason": None, "partial": partials[0] if partials else None, "partials": partials, "be": break_even}
