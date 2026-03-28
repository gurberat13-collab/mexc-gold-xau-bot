from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from utils.helpers import load_json, save_json


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    initial_quantity: float
    leverage: int
    stop_loss: float
    take_profit: float
    trailing_active: bool
    trailing_activation_price: float
    trailing_gap_pct: float
    trailing_stop: float | None
    partial_take_profit: float
    partial_close_ratio: float
    partial_taken: bool
    partial_targets: list[dict[str, Any]] = field(default_factory=list)
    break_even_trigger: float = 0.0
    break_even_done: bool = False
    opened_at: str = ""
    highest_price: float = 0.0
    lowest_price: float = 0.0
    fees_paid: float = 0.0
    reason: str = ""
    regime: str = ""
    score: int = 0
    confidence: int = 0


class PaperWallet:
    def __init__(self, path: str, starting_balance: float):
        self.path = path
        self.starting_balance = starting_balance
        self.data = load_json(
            path,
            {
                "balance": starting_balance,
                "equity": starting_balance,
                "peak_equity": starting_balance,
                "realized_pnl": 0.0,
                "daily_realized_pnl": 0.0,
                "consecutive_losses": 0,
                "trades_today": 0,
                "session_trades": 0,
                "day": datetime.now(timezone.utc).date().isoformat(),
                "open_position": None,
                "history": [],
                "equity_history": [starting_balance],
                "last_summary_day": None,
            },
        )
        self.save()

    def rollover_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.data["day"] != today:
            self.data["day"] = today
            self.data["daily_realized_pnl"] = 0.0
            self.data["consecutive_losses"] = 0
            self.data["trades_today"] = 0
            self.data["session_trades"] = 0
            self.save()

    @property
    def balance(self) -> float:
        return float(self.data["balance"])

    @property
    def open_position(self) -> dict[str, Any] | None:
        return self.data.get("open_position")

    def save(self) -> None:
        save_json(self.path, self.data)

    def can_open_new_trade(self, max_open_positions: int, max_trades_per_day: int, session_max_trades: int) -> bool:
        self.rollover_if_needed()
        if max_open_positions <= 0 or self.open_position is not None:
            return False
        if self.data["trades_today"] >= max_trades_per_day:
            return False
        if self.data["session_trades"] >= session_max_trades:
            return False
        return True

    def set_equity(self, equity: float) -> None:
        self.data["equity"] = equity
        self.data["peak_equity"] = max(float(self.data.get("peak_equity", self.starting_balance)), equity)
        self.save()

    def open_trade(self, position: Position, margin_used: float) -> None:
        self.data["balance"] -= margin_used
        self.data["open_position"] = {**asdict(position), "margin_used": margin_used}
        self.data["trades_today"] += 1
        self.data["session_trades"] += 1
        self.save()

    # FIX: close_ratio ve label parametreleri eklendi (position_manager uyumluluğu)
    def partial_close(
        self,
        exit_price: float,
        fee_rate: float,
        slippage_rate: float,
        close_ratio: float | None = None,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        pos = self.data["open_position"]
        if pos is None:
            return None

        initial_quantity = float(pos.get("initial_quantity", pos["quantity"]))
        current_quantity = float(pos["quantity"])
        if current_quantity <= 0:
            return None

        ratio = float(close_ratio if close_ratio is not None else pos.get("partial_close_ratio", 0))
        qty   = min(current_quantity, max(initial_quantity * ratio, 0.0))
        if qty <= 0:
            return None

        entry = float(pos["entry_price"])
        side  = pos["side"]
        exit_slippage  = exit_price * slippage_rate
        effective_exit = exit_price - exit_slippage if side == "long" else exit_price + exit_slippage
        gross = (effective_exit - entry) * qty if side == "long" else (entry - effective_exit) * qty
        fee   = abs(effective_exit * qty) * fee_rate
        net   = gross - fee

        margin_used      = float(pos["margin_used"])
        released_margin  = margin_used * (qty / current_quantity)
        self.data["balance"]             += released_margin + net
        self.data["realized_pnl"]        += net
        self.data["daily_realized_pnl"]  += net

        pos["quantity"]   = round(current_quantity - qty, 6)
        pos["margin_used"] = round(margin_used - released_margin, 6)
        pos["fees_paid"]  = round(float(pos.get("fees_paid", 0.0)) + fee, 6)

        # Mark the specific partial target as hit
        if label:
            targets = pos.get("partial_targets", [])
            for target in targets:
                if target.get("label") == label:
                    target["hit"] = True
            pos["partial_targets"] = targets

        # Mark fully partial_taken when all targets hit
        if not any(not t.get("hit", False) for t in pos.get("partial_targets", [])):
            pos["partial_taken"] = True

        self.data["open_position"] = pos
        self.save()
        return {
            "symbol":    pos["symbol"],
            "side":      side,
            "label":     label or "partial",
            "qty_closed": qty,
            "net_pnl":   net,
            "price":     effective_exit,
        }

    def close_trade(
        self,
        exit_price: float,
        exit_reason: str,
        fee_rate: float,
        slippage_rate: float,
    ) -> dict[str, Any]:
        pos = self.data["open_position"]
        if pos is None:
            raise RuntimeError("No open position to close")

        qty          = float(pos["quantity"])
        entry        = float(pos["entry_price"])
        side         = pos["side"]
        margin_used  = float(pos["margin_used"])
        exit_slip    = exit_price * slippage_rate
        effective_exit = exit_price - exit_slip if side == "long" else exit_price + exit_slip
        gross        = (effective_exit - entry) * qty if side == "long" else (entry - effective_exit) * qty
        close_fee    = abs(effective_exit * qty) * fee_rate
        carried_fees = float(pos.get("fees_paid", 0.0))
        net          = gross - close_fee - carried_fees

        self.data["balance"]            += margin_used + net
        self.data["realized_pnl"]       += net
        self.data["daily_realized_pnl"] += net
        self.data["consecutive_losses"]  = self.data["consecutive_losses"] + 1 if net < 0 else 0

        trade = {
            **pos,
            "exit_price":  round(effective_exit, 6),
            "exit_reason": exit_reason,
            "gross_pnl":   round(gross, 6),
            "net_pnl":     round(net, 6),
            "closed_at":   datetime.now(timezone.utc).isoformat(),
            "total_fees":  round(carried_fees + close_fee, 6),
        }
        self.data["history"]       = [trade] + self.data["history"][:199]
        self.data["open_position"] = None
        self.data["equity"]        = self.data["balance"]
        self.data["peak_equity"]   = max(
            float(self.data.get("peak_equity", self.starting_balance)),
            float(self.data["equity"]),
        )
        eh = self.data.get("equity_history", [])
        eh.append(float(self.data["equity"]))
        self.data["equity_history"] = eh[-200:]
        self.save()
        return trade

    def update_open_position(self, position: dict[str, Any]) -> None:
        self.data["open_position"] = position
        self.save()

    def performance_summary(self) -> dict[str, float | int]:
        history      = self.data.get("history", [])
        wins         = sum(1 for t in history if t.get("net_pnl", 0) > 0)
        losses       = sum(1 for t in history if t.get("net_pnl", 0) < 0)
        gross_profit = sum(t.get("net_pnl", 0) for t in history if t.get("net_pnl", 0) > 0)
        gross_loss   = -sum(t.get("net_pnl", 0) for t in history if t.get("net_pnl", 0) < 0)
        avg_win      = gross_profit / wins   if wins   else 0
        avg_loss     = gross_loss  / losses  if losses else 0
        expectancy   = ((wins / len(history)) * avg_win - (losses / len(history)) * avg_loss) if history else 0
        peak_equity  = float(self.data.get("peak_equity", self.starting_balance))
        cur_equity   = float(self.data.get("equity", self.balance))
        max_dd_pct   = max(0.0, ((peak_equity - cur_equity) / peak_equity * 100) if peak_equity else 0.0)
        by_symbol: dict[str, float] = {}
        for trade in history:
            sym = trade.get("symbol", "NA")
            by_symbol.setdefault(sym, 0.0)
            by_symbol[sym] += float(trade.get("net_pnl", 0))
        return {
            "trades":            len(history),
            "wins":              wins,
            "losses":            losses,
            "win_rate":          (wins / len(history) * 100) if history else 0,
            "profit_factor":     (gross_profit / gross_loss) if gross_loss > 0 else 0,
            "realized_pnl":      self.data["realized_pnl"],
            "daily_realized_pnl": self.data["daily_realized_pnl"],
            "expectancy":        expectancy,
            "avg_win":           avg_win,
            "avg_loss":          avg_loss,
            "max_drawdown_pct":  max_dd_pct,
            "by_symbol":         by_symbol,
        }
