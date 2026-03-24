from __future__ import annotations

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


class TelegramController:
    def __init__(self, config, scanner, wallet, client, strategy, logger):
        self.cfg = config
        self.scanner = scanner
        self.wallet = wallet
        self.client = client
        self.strategy = strategy
        self.logger = logger
        self.app = Application.builder().token(self.cfg.telegram_token).build()
        for name, fn in [
            ("start", self.start_cmd), ("baslat", self.baslat_cmd), ("durdur", self.durdur_cmd),
            ("durum", self.durum_cmd), ("bakiye", self.bakiye_cmd), ("gecmis", self.gecmis_cmd),
            ("analiz", self.analiz_cmd), ("ayar", self.ayar_cmd), ("pozisyon", self.pozisyon_cmd),
            ("rapor", self.rapor_cmd), ("sonislem", self.sonislem_cmd), ("aciklama", self.aciklama_cmd),
            ("seans", self.seans_cmd), ("riskayar", self.riskayar_cmd), ("backtest", self.backtest_cmd),
            ("mod", self.mod_cmd), ("sessiz", self.sessiz_cmd),
        ]:
            self.app.add_handler(CommandHandler(name, fn))

    async def notify(self, text: str) -> None:
        if self.cfg.telegram_chat_id:
            await self.app.bot.send_message(chat_id=self.cfg.telegram_chat_id, text=text)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "🤖 MEXC Futures Paper Bot\n"
            "Komutlar:\n"
            "/baslat /durdur /durum /pozisyon /bakiye /gecmis\n"
            "/analiz /analiz XAUT /analiz NAS100\n"
            "/rapor /sonislem /aciklama /seans /riskayar /backtest XAUT\n"
            "/mod agresif veya /mod sakin"
        )
        await update.message.reply_text(text)

    async def baslat_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.scanner.running = True
        await update.message.reply_text(f"✅ Bot aktif. Mod: {self.cfg.risk_mode.upper()}")

    async def durdur_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.scanner.running = False
        await update.message.reply_text("⏸ Bot pasif. Açık pozisyon varsa yönetmeye devam eder, yeni pozisyon açmaz.")

    async def mod_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text(f"Mevcut mod: {self.cfg.risk_mode.upper()}\nKullanım: /mod agresif veya /mod sakin")
            return
        arg = context.args[0].lower()
        if arg in ("agresif", "aggressive"):
            self.cfg.risk_mode = "aggressive"
        elif arg in ("sakin", "calm"):
            self.cfg.risk_mode = "calm"
        else:
            await update.message.reply_text("Geçersiz mod. /mod agresif veya /mod sakin")
            return
        await update.message.reply_text(f"✅ Mod değişti: {self.cfg.risk_mode.upper()}")

    async def sessiz_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.scanner.running = False
        await update.message.reply_text("🔕 Bot yeni işlem açmayacak. Açık pozisyon yoksa sessize alınmış gibi davranır.")

    async def durum_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pos = self.wallet.open_position
        summary = self.wallet.performance_summary()
        if pos:
            text = (
                f"📊 Bot: {'AKTIF' if self.scanner.running else 'PASIF'}\n"
                f"Mod: {self.cfg.risk_mode.upper()}\n"
                f"Açık Pozisyon: {pos['symbol']} {pos['side']}\n"
                f"Rejim: {pos.get('regime')} | Skor: {pos.get('score')}\n"
                f"Giriş: {pos['entry_price']:.2f}\n"
                f"SL: {pos['stop_loss']:.2f} | TP: {pos['take_profit']:.2f}\n"
                f"Trailing: {'ACIK' if pos['trailing_active'] else 'BEKLIYOR'}\n"
                f"Win rate: {summary['win_rate']:.1f}%"
            )
        else:
            text = (
                f"📊 Bot: {'AKTIF' if self.scanner.running else 'PASIF'}\n"
                f"Mod: {self.cfg.risk_mode.upper()}\n"
                f"Açık pozisyon yok.\n"
                f"Win rate: {summary['win_rate']:.1f}%"
            )
        await update.message.reply_text(text)

    async def pozisyon_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        pos = self.wallet.open_position
        if not pos:
            await update.message.reply_text("Açık pozisyon yok.")
            return
        text = (
            f"📌 Pozisyon\n"
            f"{pos['symbol']} {pos['side']}\n"
            f"Qty: {pos['quantity']:.6f}\n"
            f"Giriş: {pos['entry_price']:.2f}\n"
            f"SL: {pos['stop_loss']:.2f} | TP: {pos['take_profit']:.2f}\n"
            f"Partial TP: {pos['partial_take_profit']:.2f}\n"
            f"BE Trigger: {pos['break_even_trigger']:.2f}\n"
            f"Trailing Stop: {pos['trailing_stop'] if pos['trailing_stop'] else 'Bekliyor'}\n"
            f"Açılış: {pos['opened_at']}"
        )
        await update.message.reply_text(text)

    async def bakiye_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.wallet.rollover_if_needed()
        text = (
            f"💼 Sanal Cüzdan\n"
            f"Bakiye: {self.wallet.data['balance']:.2f} USDT\n"
            f"Equity: {self.wallet.data['equity']:.2f} USDT\n"
            f"Gerçekleşen PnL: {self.wallet.data['realized_pnl']:.2f} USDT\n"
            f"Günlük PnL: {self.wallet.data['daily_realized_pnl']:.2f} USDT"
        )
        await update.message.reply_text(text)

    async def gecmis_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        history = self.wallet.data.get("history", [])[:8]
        if not history:
            await update.message.reply_text("Henüz kapanmış işlem yok.")
            return
        lines = ["🧾 Son İşlemler"]
        for trade in history:
            lines.append(f"{trade['symbol']} {trade['side']} | {trade['exit_reason']} | {trade['net_pnl']:.2f} USDT")
        await update.message.reply_text("\n".join(lines))

    async def sonislem_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        history = self.wallet.data.get("history", [])
        if not history:
            await update.message.reply_text("Henüz kapanmış işlem yok.")
            return
        t = history[0]
        await update.message.reply_text(
            f"🧾 Son işlem\n"
            f"{t['symbol']} {t['side']}\n"
            f"Çıkış: {t['exit_reason']}\n"
            f"Net PnL: {t['net_pnl']:.2f} USDT\n"
            f"Açılış: {t['opened_at']}\n"
            f"Kapanış: {t['closed_at']}"
        )

    async def analiz_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Kullanım: /analiz XAUT")
            return

        raw = context.args[0].upper().replace("USDT", "").replace("/", "").strip()
        symbol_alias = {
            "XAUT": "XAUT_USDT",
            "XAU": "XAUT_USDT",
            "GOLD": "XAUT_USDT",
            "NAS100": "NAS100_USDT",
            "NASDAQ": "NAS100_USDT",
        }
        symbol = symbol_alias.get(raw, f"{raw}_USDT")

        try:
            df = self.client.get_klines(symbol, self.cfg.primary_timeframe, self.cfg.kline_limit)
            df_htf = self.client.get_klines(symbol, self.cfg.htf_timeframe, self.cfg.htf_kline_limit)
            snapshot = self.client.get_ticker(symbol)
            signal = self.strategy.analyze(symbol, df, df_htf)

            text = (
                f"🧠 {symbol}\nFiyat: {snapshot.last_price:.2f}\nSkor: {signal.score}\nGüven: {signal.confidence}/100\nAksiyon: {signal.action.upper()}\n"
                f"Rejim: {signal.regime} | Profil: {signal.profile}\nRSI: {signal.rsi_value:.2f}\nMACD Hist: {signal.macd_hist:.4f}\n"
                f"ADX: {signal.adx_value:.2f}\nVWAP: {signal.vwap_value:.2f}\nVol Ratio: {signal.volume_ratio:.2f}\n"
                f"HTF Bias: {signal.htf_bias} | HTF SR: {signal.htf_sr_bias}\nFunding: {snapshot.funding_rate:.5f}\nSebep: {signal.reason}"
            )
            await update.message.reply_text(text)

        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 'unknown'
            await update.message.reply_text(f"❌ {symbol} analiz hatası: HTTPError {code}")

        except Exception as exc:
            await update.message.reply_text(f"❌ {symbol} analiz hatası: {exc}")

    async def aciklama_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.wallet.open_position:
            await update.message.reply_text("Açık pozisyon yok. /analiz ile güncel sinyal sebeplerini görebilirsin.")
            return
        pos = self.wallet.open_position
        await update.message.reply_text(
            f"📝 Pozisyon Açıklaması\n"
            f"{pos['symbol']} {pos['side']}\n"
            f"Rejim: {pos.get('regime')}\n"
            f"Skor: {pos.get('score')}\n"
            f"Sebep: {pos.get('reason')}"
        )

    async def rapor_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        stats = self.wallet.performance_summary()
        by_symbol = stats.get("by_symbol", {})
        symbol_text = "\n".join([f"- {k}: {v:.2f} USDT" for k, v in by_symbol.items()]) if by_symbol else "Yok"
        txt = (
            f"📈 Rapor\n"
            f"İşlem: {stats['trades']}\n"
            f"Kazanan: {stats['wins']}\n"
            f"Kaybeden: {stats['losses']}\n"
            f"Win rate: {stats['win_rate']:.1f}%\n"
            f"Profit factor: {stats['profit_factor']:.2f}\n"
            f"Expectancy: {stats['expectancy']:.2f}\n"
            f"Avg Win: {stats['avg_win']:.2f}\n"
            f"Avg Loss: {stats['avg_loss']:.2f}\n"
            f"Max DD: {stats['max_drawdown_pct']:.2f}%\n"
            f"Toplam PnL: {stats['realized_pnl']:.2f} USDT\n"
            f"Günlük PnL: {stats['daily_realized_pnl']:.2f} USDT\n"
            f"Sembol Bazlı:\n{symbol_text}"
        )
        await update.message.reply_text(txt)

    async def seans_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            f"🕒 Seanslar (UTC)\n"
            f"XAUT: {self.cfg.xaut_session_utc} | Prefer: {self.cfg.xaut_preferred_hours}\n"
            f"NAS100: {self.cfg.nas100_session_utc} | Prefer: {self.cfg.nas100_preferred_hours}\n"
            f"Session max trades: {self.cfg.session_max_trades}\n"
            f"News filter: {'AÇIK' if self.cfg.use_news_filter else 'KAPALI'} ({self.cfg.news_blackout_hours_utc})"
        )

    async def riskayar_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            f"⚙️ Risk Ayarları\n"
            f"Mod: {self.cfg.risk_mode.upper()}\n"
            f"Kaldıraç: {self.cfg.leverage}x\n"
            f"Risk/işlem: %{self.cfg.risk_per_trade*100:.1f}\n"
            f"Günlük zarar limiti: %{self.cfg.daily_loss_limit_pct*100:.1f}\n"
            f"BE R: {self.cfg.break_even_r}\n"
            f"Partial TP R: {self.cfg.partial_tp_r}\n"
            f"Trailing gap: %{self.cfg.trailing_gap_pct*100:.2f}\n"
            f"Time stop: {self.cfg.time_stop_minutes} dk\n"
            f"Confidence min: {self.cfg.mode_confidence_min()}\n"
            f"Threshold: {self.cfg.mode_threshold()}"
        )
        await update.message.reply_text(text)

    async def ayar_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            f"⚙️ Ayarlar\n"
            f"Mod: {self.cfg.risk_mode.upper()}\n"
            f"Kaldıraç: {self.cfg.leverage}x\n"
            f"Risk/işlem: %{self.cfg.risk_per_trade*100:.1f}\n"
            f"Tarama aralığı: {self.cfg.scan_interval_seconds}s\n"
            f"TF: {self.cfg.primary_timeframe}/{self.cfg.htf_timeframe}\n"
            f"Semboller: {', '.join(self.cfg.symbols)}"
        )
        await update.message.reply_text(text)

    async def backtest_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Kullanım: /backtest XAUT veya /backtest NAS100")
            return
        raw = context.args[0].upper().replace("USDT", "").replace("/", "").strip()
        alias_map = {
            "XAUT": "XAUT_USDT",
            "XAU": "XAUT_USDT",
            "GOLD": "XAUT_USDT",
            "NAS100": "NAS100_USDT",
            "NASDAQ": "NAS100_USDT",
        }
        symbol = alias_map.get(raw, f"{raw}_USDT")
        df = self.client.get_klines(symbol, self.cfg.primary_timeframe, 300)
        df_htf = self.client.get_klines(symbol, self.cfg.htf_timeframe, 300)
        wins = losses = holds = 0
        pnl = 0.0
        for i in range(80, len(df) - 4):
            signal = self.strategy.analyze(
                symbol,
                df.iloc[:i].copy(),
                df_htf.iloc[: max(60, min(len(df_htf), i // 4 + 60))].copy(),
            )
            if signal.action == "hold":
                holds += 1
                continue
            entry = float(df.iloc[i]["close"])
            future = df.iloc[i + 1:i + 5]
            exit_price = float(future.iloc[-1]["close"])
            trade_pnl = (exit_price - entry) if signal.action == "long" else (entry - exit_price)
            pnl += trade_pnl
            if trade_pnl > 0:
                wins += 1
            else:
                losses += 1
        total = wins + losses
        await update.message.reply_text(
            f"🧪 Mini Backtest {symbol}\n"
            f"Trade: {total}\n"
            f"Win: {wins}\n"
            f"Loss: {losses}\n"
            f"Hold: {holds}\n"
            f"Ham PnL puanı: {pnl:.2f}\n"
            f"Not: Bu hızlı doğrulama testidir, tam backtest değildir."
        )

    async def start_polling(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
