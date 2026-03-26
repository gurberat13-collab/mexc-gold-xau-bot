from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BacktestResult:
    trades: int
    wins: int
    losses: int
    holds: int
    net_pnl: float
    balance: float
    win_rate: float
    segments: list[dict[str, Any]]


class Backtester:
    def __init__(self, config, strategy, risk_manager, scanner):
        self.cfg = config
        self.strategy = strategy
        self.risk = risk_manager
        self.scanner = scanner

    def _htf_history_until(self, df_htf, signal_time):
        if df_htf.empty or "time" not in df_htf:
            return df_htf.iloc[0:0].copy()
        return df_htf[df_htf["time"] <= signal_time].copy()

    def _apply_session_bonus(self, symbol: str, signal, signal_time) -> None:
        bonus = self.scanner.preferred_session_bonus(symbol, signal_time) * self.cfg.preferred_session_confidence_bonus
        if bonus:
            signal.confidence = min(100, signal.confidence + bonus)
            signal.action = self.strategy.determine_action(signal.score, signal.confidence, signal.regime)

    def _effective_entry_price(self, side: str, raw_price: float) -> float:
        if side == "long":
            return raw_price + (raw_price * self.cfg.slippage_rate)
        return raw_price - (raw_price * self.cfg.slippage_rate)

    def _effective_exit_price(self, side: str, raw_price: float) -> float:
        if side == "long":
            return raw_price - (raw_price * self.cfg.slippage_rate)
        return raw_price + (raw_price * self.cfg.slippage_rate)

    def _simulate_trade(self, symbol: str, signal, future_bars, balance: float) -> dict[str, Any] | None:
        horizon = future_bars.iloc[: self.cfg.backtest_max_hold_bars].copy()
        if horizon.empty:
            return None

        entry_price = float(horizon.iloc[0]["open"])
        plan = self.risk.build_plan(
            symbol,
            signal.action,
            entry_price,
            signal.atr_value,
            balance,
            signal.regime,
            signal.confidence,
        )
        quantity = float(plan.quantity)
        if quantity <= 0:
            return None

        side = signal.action
        remaining_qty = quantity
        initial_qty = quantity
        entry_effective = self._effective_entry_price(side, entry_price)
        fees_paid = abs(entry_effective * quantity) * self.cfg.fee_rate
        partial_targets = [dict(target) for target in plan.partial_targets]
        stop_loss = float(plan.stop_loss)
        trailing_active = False
        trailing_stop = None
        break_even_done = False
        highest_price = entry_effective
        lowest_price = entry_effective
        realized = 0.0
        exit_reason = "time_window"
        exit_price = float(horizon.iloc[-1]["close"])

        # Conservative intrabar rule: if both stop and target are inside the same bar, adverse side wins first.
        bars_held = 0
        for bars_held, (_, bar) in enumerate(horizon.iterrows(), start=1):
            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])
            highest_price = max(highest_price, high)
            lowest_price = min(lowest_price, low)

            if side == "long":
                if low <= stop_loss:
                    exit_reason = "stop_loss"
                    exit_price = stop_loss
                    break
                if trailing_active and trailing_stop is not None and low <= trailing_stop:
                    exit_reason = "trailing_stop"
                    exit_price = float(trailing_stop)
                    break
                for target in partial_targets:
                    if target.get("hit"):
                        continue
                    if high < float(target["price"]):
                        continue
                    qty_to_close = min(remaining_qty, initial_qty * float(target["close_ratio"]))
                    if qty_to_close <= 0:
                        target["hit"] = True
                        continue
                    partial_exit = self._effective_exit_price(side, float(target["price"]))
                    partial_gross = (partial_exit - entry_effective) * qty_to_close
                    partial_fee = abs(partial_exit * qty_to_close) * self.cfg.fee_rate
                    realized += partial_gross - partial_fee
                    fees_paid += partial_fee
                    remaining_qty = max(0.0, remaining_qty - qty_to_close)
                    target["hit"] = True
                if not break_even_done and high >= float(plan.break_even_trigger):
                    stop_loss = max(stop_loss, entry_effective)
                    break_even_done = True
                if not trailing_active and high >= float(plan.trailing_activation_price):
                    trailing_active = True
                    trailing_stop = high * (1 - float(plan.trailing_gap_pct))
                elif trailing_active and trailing_stop is not None:
                    trailing_stop = max(float(trailing_stop), highest_price * (1 - float(plan.trailing_gap_pct)))
                if high >= float(plan.take_profit):
                    exit_reason = "take_profit"
                    exit_price = float(plan.take_profit)
                    break
            else:
                if high >= stop_loss:
                    exit_reason = "stop_loss"
                    exit_price = stop_loss
                    break
                if trailing_active and trailing_stop is not None and high >= trailing_stop:
                    exit_reason = "trailing_stop"
                    exit_price = float(trailing_stop)
                    break
                for target in partial_targets:
                    if target.get("hit"):
                        continue
                    if low > float(target["price"]):
                        continue
                    qty_to_close = min(remaining_qty, initial_qty * float(target["close_ratio"]))
                    if qty_to_close <= 0:
                        target["hit"] = True
                        continue
                    partial_exit = self._effective_exit_price(side, float(target["price"]))
                    partial_gross = (entry_effective - partial_exit) * qty_to_close
                    partial_fee = abs(partial_exit * qty_to_close) * self.cfg.fee_rate
                    realized += partial_gross - partial_fee
                    fees_paid += partial_fee
                    remaining_qty = max(0.0, remaining_qty - qty_to_close)
                    target["hit"] = True
                if not break_even_done and low <= float(plan.break_even_trigger):
                    stop_loss = min(stop_loss, entry_effective)
                    break_even_done = True
                if not trailing_active and low <= float(plan.trailing_activation_price):
                    trailing_active = True
                    trailing_stop = low * (1 + float(plan.trailing_gap_pct))
                elif trailing_active and trailing_stop is not None:
                    trailing_stop = min(float(trailing_stop), lowest_price * (1 + float(plan.trailing_gap_pct)))
                if low <= float(plan.take_profit):
                    exit_reason = "take_profit"
                    exit_price = float(plan.take_profit)
                    break

            exit_price = close

        final_pnl = 0.0
        if remaining_qty > 0:
            effective_exit = self._effective_exit_price(side, exit_price)
            if side == "long":
                final_pnl = (effective_exit - entry_effective) * remaining_qty
            else:
                final_pnl = (entry_effective - effective_exit) * remaining_qty
            final_pnl -= abs(effective_exit * remaining_qty) * self.cfg.fee_rate

        net_pnl = realized + final_pnl - abs(entry_effective * quantity) * self.cfg.fee_rate
        return {
            "net_pnl": net_pnl,
            "reason": exit_reason,
            "bars_held": max(1, bars_held),
        }

    def _run_index_range(self, symbol: str, df, df_htf, start_idx: int, end_idx: int, starting_balance: float) -> dict[str, Any]:
        balance = starting_balance
        wins = losses = holds = 0
        pnl = 0.0
        warmup = max(self.cfg.backtest_min_bars, self.cfg.breakout_lookback + 5, self.cfg.sr_lookback + 5)

        i = max(start_idx, warmup)
        while i < min(end_idx, len(df) - 1):
            history = df.iloc[:i].copy()
            if history.empty:
                i += 1
                continue
            signal_time = history.iloc[-1]["time"]
            if self.scanner.in_news_blackout(signal_time):
                holds += 1
                i += 1
                continue
            if not self.scanner.in_session(symbol, signal_time):
                holds += 1
                i += 1
                continue

            signal = self.strategy.analyze(symbol, history, self._htf_history_until(df_htf, signal_time))
            self._apply_session_bonus(symbol, signal, signal_time)
            if signal.action == "hold":
                holds += 1
                i += 1
                continue

            result = self._simulate_trade(symbol, signal, df.iloc[i:], balance)
            if result is None:
                holds += 1
                i += 1
                continue

            trade_pnl = float(result["net_pnl"])
            pnl += trade_pnl
            balance += trade_pnl
            if trade_pnl > 0:
                wins += 1
            else:
                losses += 1
            i += max(1, int(result.get("bars_held", 1)))

        trades = wins + losses
        return {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "holds": holds,
            "net_pnl": pnl,
            "balance": balance,
            "win_rate": (wins / trades * 100) if trades else 0.0,
        }

    def run(self, symbol: str, df, df_htf, walk_forward: bool = False) -> BacktestResult:
        if not walk_forward:
            result = self._run_index_range(symbol, df, df_htf, 0, len(df), self.cfg.starting_balance)
            return BacktestResult(segments=[], **result)

        segments: list[dict[str, Any]] = []
        balance = self.cfg.starting_balance
        warmup = max(self.cfg.backtest_min_bars, self.cfg.breakout_lookback + 5, self.cfg.sr_lookback + 5)
        usable = max(0, len(df) - warmup)
        splits = max(2, self.cfg.backtest_wf_splits)
        segment_size = max(1, usable // splits)

        total = {"trades": 0, "wins": 0, "losses": 0, "holds": 0, "net_pnl": 0.0}
        for idx in range(splits):
            start_idx = warmup + (idx * segment_size)
            end_idx = len(df) if idx == splits - 1 else min(len(df), start_idx + segment_size)
            segment = self._run_index_range(symbol, df, df_htf, start_idx, end_idx, balance)
            balance = segment["balance"]
            segments.append(
                {
                    "label": f"WF-{idx + 1}",
                    "start": int(start_idx),
                    "end": int(end_idx),
                    **segment,
                }
            )
            for key in total:
                total[key] += segment[key]

        trades = total["trades"]
        return BacktestResult(
            trades=trades,
            wins=total["wins"],
            losses=total["losses"],
            holds=total["holds"],
            net_pnl=total["net_pnl"],
            balance=balance,
            win_rate=(total["wins"] / trades * 100) if trades else 0.0,
            segments=segments,
        )
