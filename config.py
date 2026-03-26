from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _getenv_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


@dataclass
class BotConfig:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
    primary_timeframe: str = os.getenv("PRIMARY_TIMEFRAME", "Min15")
    htf_timeframe: str = os.getenv("HTF_TIMEFRAME", "Min60")
    kline_limit: int = int(os.getenv("KLINE_LIMIT", "260"))
    htf_kline_limit: int = int(os.getenv("HTF_KLINE_LIMIT", "260"))

    symbols: List[str] = field(default_factory=lambda: os.getenv("SYMBOLS", "XAUT_USDT,NAS100_USDT").split(","))

    starting_balance: float = float(os.getenv("STARTING_BALANCE", "1000"))
    leverage: int = int(os.getenv("LEVERAGE", "5"))
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.03"))
    daily_loss_limit_pct: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.08"))
    max_consecutive_losses: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "1"))
    max_trades_per_day: int = int(os.getenv("MAX_TRADES_PER_DAY", "12"))
    cooldown_minutes: int = int(os.getenv("COOLDOWN_MINUTES", "10"))

    fee_rate: float = float(os.getenv("FEE_RATE", "0.0004"))
    slippage_rate: float = float(os.getenv("SLIPPAGE_RATE", "0.0003"))

    breakout_lookback: int = int(os.getenv("BREAKOUT_LOOKBACK", "20"))
    atr_period: int = int(os.getenv("ATR_PERIOD", "14"))
    atr_stop_mult: float = float(os.getenv("ATR_STOP_MULT", "1.4"))
    rr_ratio: float = float(os.getenv("RR_RATIO", "2.2"))
    trailing_activation_r: float = float(os.getenv("TRAILING_ACTIVATION_R", "1.15"))
    trailing_gap_pct: float = float(os.getenv("TRAILING_GAP_PCT", "0.008"))
    break_even_r: float = float(os.getenv("BREAK_EVEN_R", "0.85"))
    partial_tp_r: float = float(os.getenv("PARTIAL_TP_R", "1.3"))
    partial_close_ratio: float = float(os.getenv("PARTIAL_CLOSE_RATIO", "0.35"))
    secondary_partial_tp_r: float = float(os.getenv("SECONDARY_PARTIAL_TP_R", "1.8"))
    secondary_partial_close_ratio: float = float(os.getenv("SECONDARY_PARTIAL_CLOSE_RATIO", "0.25"))
    time_stop_minutes: int = int(os.getenv("TIME_STOP_MINUTES", "180"))

    aggressive_score_threshold: int = int(os.getenv("AGGRESSIVE_SCORE_THRESHOLD", "3"))
    calm_score_threshold: int = int(os.getenv("CALM_SCORE_THRESHOLD", "3"))
    confidence_min_aggressive: int = int(os.getenv("CONFIDENCE_MIN_AGGRESSIVE", "48"))
    confidence_min_calm: int = int(os.getenv("CONFIDENCE_MIN_CALM", "58"))
    risk_mode: str = os.getenv("RISK_MODE", "aggressive").lower()

    funding_abs_limit: float = float(os.getenv("FUNDING_ABS_LIMIT", "0.0025"))
    max_last_candle_pct: float = float(os.getenv("MAX_LAST_CANDLE_PCT", "0.025"))
    max_spread_pct: float = float(os.getenv("MAX_SPREAD_PCT", "0.0025"))
    adx_trend_threshold: float = float(os.getenv("ADX_TREND_THRESHOLD", "18"))
    vwap_distance_limit: float = float(os.getenv("VWAP_DISTANCE_LIMIT", "0.012"))
    volatile_atr_ratio: float = float(os.getenv("VOLATILE_ATR_RATIO", "0.013"))
    require_trending_regime: bool = _getenv_bool("REQUIRE_TRENDING_REGIME", "false")

    ema_distance_threshold: float = float(os.getenv("EMA_DISTANCE_THRESHOLD", "0.0018"))
    sr_lookback: int = int(os.getenv("SR_LOOKBACK", "48"))
    sr_atr_tolerance: float = float(os.getenv("SR_ATR_TOLERANCE", "0.65"))
    rsi_divergence_lookback: int = int(os.getenv("RSI_DIVERGENCE_LOOKBACK", "8"))
    rsi_divergence_min_delta: float = float(os.getenv("RSI_DIVERGENCE_MIN_DELTA", "4.0"))
    preferred_session_confidence_bonus: int = int(os.getenv("PREFERRED_SESSION_CONFIDENCE_BONUS", "5"))
    opposite_signal_confidence_min: int = int(os.getenv("OPPOSITE_SIGNAL_CONFIDENCE_MIN", "65"))
    profitable_time_stop_extension: float = float(os.getenv("PROFITABLE_TIME_STOP_EXTENSION", "1.5"))

    confidence_size_boost_threshold: int = int(os.getenv("CONFIDENCE_SIZE_BOOST_THRESHOLD", "80"))
    confidence_size_reduce_threshold: int = int(os.getenv("CONFIDENCE_SIZE_REDUCE_THRESHOLD", "50"))
    confidence_size_boost_multiplier: float = float(os.getenv("CONFIDENCE_SIZE_BOOST_MULTIPLIER", "1.1"))
    confidence_size_reduce_multiplier: float = float(os.getenv("CONFIDENCE_SIZE_REDUCE_MULTIPLIER", "0.7"))

    use_session_filter: bool = _getenv_bool("USE_SESSION_FILTER", "true")
    xaut_session_utc: str = os.getenv("XAUT_SESSION_UTC", "05-22")
    nas100_session_utc: str = os.getenv("NAS100_SESSION_UTC", "12-21")
    session_max_trades: int = int(os.getenv("SESSION_MAX_TRADES", "10"))
    xaut_preferred_hours: str = os.getenv("XAUT_PREFERRED_HOURS", "07-11,13-17")
    nas100_preferred_hours: str = os.getenv("NAS100_PREFERRED_HOURS", "13-17,18-20")

    use_news_filter: bool = _getenv_bool("USE_NEWS_FILTER", "false")
    news_blackout_hours_utc: str = os.getenv("NEWS_BLACKOUT_HOURS_UTC", "13,14")

    backtest_default_limit: int = int(os.getenv("BACKTEST_DEFAULT_LIMIT", "600"))
    backtest_min_bars: int = int(os.getenv("BACKTEST_MIN_BARS", "120"))
    backtest_max_hold_bars: int = int(os.getenv("BACKTEST_MAX_HOLD_BARS", "24"))
    backtest_wf_splits: int = int(os.getenv("BACKTEST_WF_SPLITS", "3"))

    use_nas100_asia_model: bool = _getenv_bool("USE_NAS100_ASIA_MODEL", "true")
    ny_timezone: str = os.getenv("NY_TIMEZONE", "America/New_York")
    nas100_model_timeframe: str = os.getenv("NAS100_MODEL_TIMEFRAME", "Min5")
    nas100_model_kline_limit: int = int(os.getenv("NAS100_MODEL_KLINE_LIMIT", "720"))
    asia_range_ny: str = os.getenv("ASIA_RANGE_NY", "20:00-03:00")
    nas100_preopen_window_ny: str = os.getenv("NAS100_PREOPEN_WINDOW_NY", "08:00-09:29")
    nas100_open_window_ny: str = os.getenv("NAS100_OPEN_WINDOW_NY", "09:30-09:50")
    nas100_macro_windows_ny: str = os.getenv("NAS100_MACRO_WINDOWS_NY", "09:50-10:10,10:50-11:00,11:10-11:30,11:50-12:00")
    asia_range_max_width_atr: float = float(os.getenv("ASIA_RANGE_MAX_WIDTH_ATR", "6.5"))
    asia_range_max_drift_ratio: float = float(os.getenv("ASIA_RANGE_MAX_DRIFT_RATIO", "0.55"))
    asia_sweep_min_atr: float = float(os.getenv("ASIA_SWEEP_MIN_ATR", "0.12"))
    cisd_displacement_atr: float = float(os.getenv("CISD_DISPLACEMENT_ATR", "0.45"))
    fvg_eq_tolerance_atr: float = float(os.getenv("FVG_EQ_TOLERANCE_ATR", "0.18"))
    asia_model_confidence_floor: int = int(os.getenv("ASIA_MODEL_CONFIDENCE_FLOOR", "60"))

    state_path: str = os.getenv("STATE_PATH", "storage/state.json")
    wallet_path: str = os.getenv("WALLET_PATH", "storage/wallet.json")
    trades_path: str = os.getenv("TRADES_PATH", "storage/trades.json")
    log_path: str = os.getenv("LOG_PATH", "storage/logs.txt")

    bot_enabled: bool = _getenv_bool("BOT_ENABLED", "true")
    sim_mode: bool = _getenv_bool("SIM_MODE", "true")

    def mode_threshold(self) -> int:
        return self.aggressive_score_threshold if self.risk_mode == "aggressive" else self.calm_score_threshold

    def mode_confidence_min(self) -> int:
        return self.confidence_min_aggressive if self.risk_mode == "aggressive" else self.confidence_min_calm


CONFIG = BotConfig()
