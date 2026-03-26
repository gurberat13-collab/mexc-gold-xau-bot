from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


class ScannerEngine:
    def __init__(self, config, client, strategy, risk_manager, wallet, executor, position_manager, logger, notifier):
        self.cfg = config
        self.client = client
        self.strategy = strategy
        self.risk = risk_manager
        self.wallet = wallet
        self.executor = executor
        self.position_manager = position_manager
        self.logger = logger
        self.notifier = notifier
        self.running = False
        self.last_trade_time: datetime | None = None
        self.last_daily_summary_sent = None

    async def start(self) -> None:
        self.running = True
        self.logger.info("Scanner started")
        await self.notifier(f"Futures paper bot baslatildi. Mod: {self.cfg.risk_mode.upper()}")

    async def stop(self) -> None:
        self.running = False
        self.logger.info("Scanner stopped")
        await self.notifier("Bot durduruldu. Yeni islem acmayacak.")

    def in_cooldown(self) -> bool:
        if self.last_trade_time is None:
            return False
        return datetime.now(timezone.utc) < self.last_trade_time + timedelta(minutes=self.cfg.cooldown_minutes)

    def _analysis_time(self, df) -> datetime:
        if df is not None and not df.empty and "time" in df:
            stamp = df.iloc[-1]["time"]
            if hasattr(stamp, "to_pydatetime"):
                stamp = stamp.to_pydatetime()
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    def _utc_hour(self, reference_time: datetime | None = None) -> int:
        if reference_time is None:
            return datetime.now(timezone.utc).hour
        if hasattr(reference_time, "to_pydatetime"):
            reference_time = reference_time.to_pydatetime()
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        return reference_time.astimezone(timezone.utc).hour

    def _hour_in_range(self, start: int, end: int, hour: int) -> bool:
        if start == end:
            return True
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _parse_window(self, text: str, hour: int) -> bool:
        for chunk in text.split(","):
            start, end = [int(x) for x in chunk.split("-")]
            if self._hour_in_range(start, end, hour):
                return True
        return False

    def in_session(self, symbol: str, reference_time: datetime | None = None) -> bool:
        if not self.cfg.use_session_filter:
            return True
        hour = self._utc_hour(reference_time)
        if symbol.startswith("XAUT"):
            return self._parse_window(self.cfg.xaut_session_utc, hour)
        if symbol.startswith("NAS100"):
            return self._parse_window(self.cfg.nas100_session_utc, hour)
        return True

    def preferred_session_bonus(self, symbol: str, reference_time: datetime | None = None) -> int:
        hour = self._utc_hour(reference_time)
        if symbol.startswith("XAUT") and self._parse_window(self.cfg.xaut_preferred_hours, hour):
            return 1
        if symbol.startswith("NAS100") and self._parse_window(self.cfg.nas100_preferred_hours, hour):
            return 1
        return 0

    def in_news_blackout(self, reference_time: datetime | None = None) -> bool:
        if not self.cfg.use_news_filter:
            return False
        hour = self._utc_hour(reference_time)
        hours = {int(x.strip()) for x in self.cfg.news_blackout_hours_utc.split(",") if x.strip()}
        return hour in hours

    def daily_summary_text(self) -> str:
        stats = self.wallet.performance_summary()
        return (
            "Gunluk Ozet\n"
            f"Mod: {self.cfg.risk_mode.upper()}\n"
            f"Islem: {stats['trades']}\n"
            f"Win rate: {stats['win_rate']:.1f}%\n"
            f"Profit factor: {stats['profit_factor']:.2f}\n"
            f"Expectancy: {stats['expectancy']:.2f}\n"
            f"Max DD: {stats['max_drawdown_pct']:.2f}%\n"
            f"Toplam PnL: {stats['realized_pnl']:.2f} USDT\n"
            f"Gunluk PnL: {stats['daily_realized_pnl']:.2f} USDT"
        )

    async def maybe_send_daily_summary(self):
        today = datetime.now(timezone.utc).date().isoformat()
        hour = datetime.now(timezone.utc).hour
        if hour == 23 and self.last_daily_summary_sent != today:
            await self.notifier(self.daily_summary_text())
            self.last_daily_summary_sent = today

    async def _analyze_symbol(self, symbol: str):
        df = self.client.get_klines(symbol, self.cfg.primary_timeframe, self.cfg.kline_limit)
        df_htf = self.client.get_klines(symbol, self.cfg.htf_timeframe, self.cfg.htf_kline_limit)
        snapshot = self.client.get_ticker(symbol)
        signal = self.strategy.analyze(symbol, df, df_htf)
        return df, df_htf, snapshot, signal

    def _apply_session_bonus(self, symbol: str, signal, analysis_time: datetime) -> None:
        bonus = self.preferred_session_bonus(symbol, analysis_time) * self.cfg.preferred_session_confidence_bonus
        if bonus:
            signal.confidence = min(100, signal.confidence + bonus)
            signal.action = self.strategy.determine_action(signal.score, signal.confidence, signal.regime)
            signal.reason = f"{signal.reason}, Session bonus +{bonus}" if signal.reason else f"Session bonus +{bonus}"

    async def tick(self) -> None:
        self.wallet.rollover_if_needed()
        await self.maybe_send_daily_summary()

        if self.wallet.open_position:
            symbol = self.wallet.open_position["symbol"]
            df, _, snapshot, fresh_signal = await self._analyze_symbol(symbol)
            analysis_time = self._analysis_time(df)
            self._apply_session_bonus(symbol, fresh_signal, analysis_time)
            self.position_manager.mark_equity(snapshot.last_price)
            result = self.position_manager.update_and_check_exit(
                snapshot.last_price,
                fresh_signal.action,
                fresh_signal.confidence,
            )
            partials = result.get("partials") or ([] if not result.get("partial") else [result["partial"]])
            for partial in partials:
                await self.notifier(
                    "Partial TP\n"
                    f"{partial['symbol']} {partial['side']} {partial.get('label', '')}\n"
                    f"Kapanan qty: {partial['qty_closed']:.6f}\n"
                    f"PnL: {partial['net_pnl']:.2f} USDT"
                )
            if result.get("be"):
                await self.notifier(f"Break-even aktif\n{symbol} stop girise cekildi.")
            if result.get("exit") and result.get("reason"):
                trade = self.wallet.close_trade(snapshot.last_price, result["reason"], self.cfg.fee_rate, self.cfg.slippage_rate)
                self.last_trade_time = datetime.now(timezone.utc)
                msg = (
                    "Pozisyon kapandi\n"
                    f"{trade['symbol']} {trade['side']}\n"
                    f"Sebep: {trade['exit_reason']}\n"
                    f"Net PnL: {trade['net_pnl']:.2f} USDT\n"
                    f"Bakiye: {self.wallet.balance:.2f} USDT"
                )
                self.logger.info(msg.replace("\n", " | "))
                await self.notifier(msg)
            return

        if not self.running or self.in_cooldown():
            return
        if self.risk.daily_loss_breached(self.wallet):
            await self.notifier("Gunluk zarar limiti asildi. Bot bugun yeni islem acmayacak.")
            self.running = False
            return
        if self.risk.consecutive_losses_breached(self.wallet):
            await self.notifier("Ust uste stop limiti asildi. Bot durduruldu.")
            self.running = False
            return
        if not self.wallet.can_open_new_trade(self.cfg.max_open_positions, self.cfg.max_trades_per_day, self.cfg.session_max_trades):
            return

        best_signal = None
        best_snapshot = None

        for symbol in self.cfg.symbols:
            df, _, snapshot, signal = await self._analyze_symbol(symbol)
            analysis_time = self._analysis_time(df)
            if not self.in_session(symbol, analysis_time):
                continue
            if self.in_news_blackout(analysis_time):
                continue
            self._apply_session_bonus(symbol, signal, analysis_time)
            if abs(snapshot.funding_rate) > self.cfg.funding_abs_limit:
                continue
            if snapshot.spread_pct > self.cfg.max_spread_pct:
                continue
            last_candle_pct = abs((df.iloc[-1]["close"] - df.iloc[-1]["open"]) / df.iloc[-1]["open"])
            if last_candle_pct > self.cfg.max_last_candle_pct:
                continue
            if signal.action == "hold":
                continue
            if best_signal is None or (signal.confidence, abs(signal.score)) > (best_signal.confidence, abs(best_signal.score)):
                best_signal = signal
                best_snapshot = snapshot

        if best_signal and best_snapshot:
            plan = self.risk.build_plan(
                best_signal.symbol,
                best_signal.action,
                best_snapshot.last_price,
                best_signal.atr_value,
                self.wallet.balance,
                best_signal.regime,
                best_signal.confidence,
            )
            opened = self.executor.open_position(
                best_signal.symbol,
                best_signal.action,
                best_snapshot.last_price,
                plan,
                best_signal.reason,
                best_signal.regime,
                best_signal.score,
                best_signal.confidence,
            )
            self.last_trade_time = datetime.now(timezone.utc)
            msg = (
                "Yeni pozisyon acildi\n"
                f"{opened['symbol']} {opened['side']} {opened['quantity']:.6f}\n"
                f"Giris: {opened['entry_price']:.2f}\n"
                f"SL: {opened['stop_loss']:.2f} | TP: {opened['take_profit']:.2f}\n"
                f"Partial: {opened['partial_take_profit']:.2f} | BE: {opened['break_even_trigger']:.2f}\n"
                f"Rejim: {opened['regime']} | Skor: {opened['score']} | Guven: {best_signal.confidence}/100 | Mod: {self.cfg.risk_mode.upper()}"
            )
            self.logger.info(msg.replace("\n", " | "))
            await self.notifier(msg)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:
                self.logger.exception("Tick error: %s", exc)
                await self.notifier(f"Bot hatasi: {exc}")
            await asyncio.sleep(self.cfg.scan_interval_seconds)
