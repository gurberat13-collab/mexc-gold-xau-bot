from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from utils.helpers import load_json, save_json


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: float
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
    break_even_trigger: float
    break_even_done: bool
    opened_at: str
    highest_price: float
    lowest_price: float
    fees_paid: float
    reason: str
    regime: str
    score: int


class PaperWallet:
    def __init__(self, path: str, starting_balance: float):
        self.path = path
        self.starting_balance = starting_balance
        self.data = load_json(path, {
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
            "last_summary_day": None,
        })
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
        self.data["peak_equity"] = max(float(self.data.get('peak_equity', self.starting_balance)), equity)
        self.save()

    def open_trade(self, position: Position, margin_used: float) -> None:
        self.data["balance"] -= margin_used
        self.data["open_position"] = {**asdict(position), "margin_used": margin_used}
        self.data["trades_today"] += 1
        self.data["session_trades"] += 1
        self.save()

    def partial_close(self, exit_price: float, fee_rate: float, slippage_rate: float) -> dict[str, Any] | None:
        pos = self.data["open_position"]
        if pos is None or pos.get("partial_taken"):
            return None
        qty = float(pos["quantity"]) * float(pos["partial_close_ratio"])
        entry = float(pos["entry_price"])
        side = pos["side"]
        exit_slippage = exit_price * slippage_rate
        effective_exit = exit_price - exit_slippage if side == "long" else exit_price + exit_slippage
        gross = (effective_exit - entry) * qty if side == "long" else (entry - effective_exit) * qty
        fee = abs(effective_exit * qty) * fee_rate
        net = gross - fee
        released_margin = float(pos["margin_used"]) * float(pos["partial_close_ratio"])
        self.data["balance"] += released_margin + net
        self.data["realized_pnl"] += net
        self.data["daily_realized_pnl"] += net
        pos["quantity"] = round(float(pos["quantity"]) - qty, 6)
        pos["margin_used"] = round(float(pos["margin_used"]) - released_margin, 6)
        pos["fees_paid"] = round(float(pos.get("fees_paid", 0.0)) + fee, 6)
        pos["partial_taken"] = True
        self.data["open_position"] = pos
        self.save()
        return {"symbol": pos["symbol"], "side": side, "qty_closed": qty, "net_pnl": net, "price": effective_exit}

    def close_trade(self, exit_price: float, exit_reason: str, fee_rate: float, slippage_rate: float) -> dict[str, Any]:
        pos = self.data["open_position"]
        if pos is None:
            raise RuntimeError("No open position to close")
        qty = float(pos["quantity"])
        entry = float(pos["entry_price"])
        side = pos["side"]
        margin_used = float(pos["margin_used"])
        exit_slippage = exit_price * slippage_rate
        effective_exit = exit_price - exit_slippage if side == "long" else exit_price + exit_slippage
        gross = (effective_exit - entry) * qty if side == "long" else (entry - effective_exit) * qty
        close_fee = abs(effective_exit * qty) * fee_rate
        open_fee = float(pos.get("fees_paid", 0.0))
        net = gross - close_fee - open_fee
        self.data["balance"] += margin_used + net
        self.data["realized_pnl"] += net
        self.data["daily_realized_pnl"] += net
        self.data["consecutive_losses"] = self.data["consecutive_losses"] + 1 if net < 0 else 0
        trade = {
            **pos,
            "exit_price": round(effective_exit, 6),
            "exit_reason": exit_reason,
            "gross_pnl": round(gross, 6),
            "net_pnl": round(net, 6),
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "total_fees": round(open_fee + close_fee, 6),
        }
        self.data["history"] = [trade] + self.data["history"][:199]
        self.data["open_position"] = None
        self.data["equity"] = self.data["balance"]
        self.data["peak_equity"] = max(float(self.data.get('peak_equity', self.starting_balance)), float(self.data['equity']))
        self.save()
        return trade

    def update_open_position(self, position: dict[str, Any]) -> None:
        self.data["open_position"] = position
        self.save()

    def performance_summary(self) -> dict[str, float | int]:
        history = self.data.get("history", [])
        wins = sum(1 for t in history if t.get("net_pnl", 0) > 0)
        losses = sum(1 for t in history if t.get("net_pnl", 0) < 0)
        gross_profit = sum(t.get("net_pnl", 0) for t in history if t.get("net_pnl", 0) > 0)
        gross_loss = -sum(t.get("net_pnl", 0) for t in history if t.get("net_pnl", 0) < 0)
        avg_win = gross_profit / wins if wins else 0
        avg_loss = gross_loss / losses if losses else 0
        expectancy = ((wins / len(history)) * avg_win - (losses / len(history)) * avg_loss) if history else 0
        peak_equity = float(self.data.get('peak_equity', self.starting_balance))
        current_equity = float(self.data.get('equity', self.balance))
        max_dd_pct = max(0.0, ((peak_equity - current_equity) / peak_equity * 100) if peak_equity else 0.0)
        by_symbol = {}
        for t in history:
            sym = t.get('symbol', 'NA')
            by_symbol.setdefault(sym, 0.0)
            by_symbol[sym] += float(t.get('net_pnl', 0))
        return {
            "trades": len(history),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(history) * 100) if history else 0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else 0,
            "realized_pnl": self.data["realized_pnl"],
            "daily_realized_pnl": self.data["daily_realized_pnl"],
            "expectancy": expectancy,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_drawdown_pct": max_dd_pct,
            "by_symbol": by_symbol,
        }
