from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _getenv_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"

def _env_float(name: str, default: str, min_val: float = 0.0, max_val: float = float('inf')) -> float:
    val = float(os.getenv(name, default))
    return max(min_val, min(val, max_val))

def _env_int(name: str, default: str, min_val: int = 0, max_val: int = 999999) -> int:
    val = int(os.getenv(name, default))
    return max(min_val, min(val, max_val))

@dataclass(frozen=True)
class DrawdownProtectionConfig:
    tier1_drawdown_pct:    float = 0.05
    tier1_size_multiplier: float = 0.50
    tier2_drawdown_pct:    float = 0.10
    tier2_size_multiplier: float = 0.25
    max_drawdown_pct:      float = 0.15
    weekly_loss_limit_pct:  float = 0.12
    monthly_loss_limit_pct: float = 0.18
    recovery_mode_enabled:  bool  = True
    recovery_size_multiplier: float = 0.50
    recovery_exit_profit_pct: float = 0.03

    @staticmethod
    def from_env() -> DrawdownProtectionConfig:
        return DrawdownProtectionConfig(
            tier1_drawdown_pct=_env_float("TIER1_DRAWDOWN_PCT", "0.05", min_val=0.01, max_val=0.20),
            tier1_size_multiplier=_env_float("TIER1_SIZE_MULTIPLIER", "0.50", min_val=0.1, max_val=1.0),
            tier2_drawdown_pct=_env_float("TIER2_DRAWDOWN_PCT", "0.10", min_val=0.03, max_val=0.30),
            tier2_size_multiplier=_env_float("TIER2_SIZE_MULTIPLIER", "0.25", min_val=0.05, max_val=0.8),
            max_drawdown_pct=_env_float("MAX_DRAWDOWN_PCT", "0.15", min_val=0.05, max_val=0.40),
            weekly_loss_limit_pct=_env_float("WEEKLY_LOSS_LIMIT_PCT", "0.12", min_val=0.03, max_val=0.30),
            monthly_loss_limit_pct=_env_float("MONTHLY_LOSS_LIMIT_PCT", "0.18", min_val=0.05, max_val=0.40),
            recovery_mode_enabled=_getenv_bool("RECOVERY_MODE_ENABLED", "true"),
            recovery_size_multiplier=_env_float("RECOVERY_SIZE_MULTIPLIER", "0.50", min_val=0.1, max_val=1.0),
            recovery_exit_profit_pct=_env_float("RECOVERY_EXIT_PROFIT_PCT", "0.03", min_val=0.01, max_val=0.10),
        )

@dataclass(frozen=True)
class KellyCriterionConfig:
    enabled: bool = True
    fraction: float = 0.40
    min_trades_for_calculation: int = 30
    max_kelly_pct: float = 0.06
    min_kelly_pct: float = 0.005
    recalculate_every_n_trades: int = 10

    @staticmethod
    def from_env() -> KellyCriterionConfig:
        return KellyCriterionConfig(
            enabled=_getenv_bool("KELLY_ENABLED", "true"),
            fraction=_env_float("KELLY_FRACTION", "0.40", min_val=0.1, max_val=1.0),
            min_trades_for_calculation=_env_int("KELLY_MIN_TRADES", "30", min_val=10, max_val=200),
            max_kelly_pct=_env_float("KELLY_MAX_PCT", "0.06", min_val=0.01, max_val=0.15),
            min_kelly_pct=_env_float("KELLY_MIN_PCT", "0.005", min_val=0.001, max_val=0.03),
            recalculate_every_n_trades=_env_int("KELLY_RECALC_INTERVAL", "10", min_val=5, max_val=50),
        )

@dataclass(frozen=True)
class EquityCurveConfig:
    enabled: bool = True
    ema_period: int = 20
    below_ema_multiplier: float = 0.50
    hard_stop_below_ema_pct: float = 0.05
    above_ema_bonus: float = 1.0

    @staticmethod
    def from_env() -> EquityCurveConfig:
        return EquityCurveConfig(
            enabled=_getenv_bool("EQUITY_CURVE_ENABLED", "true"),
            ema_period=_env_int("EQUITY_EMA_PERIOD", "20", min_val=5, max_val=100),
            below_ema_multiplier=_env_float("EQUITY_BELOW_EMA_MULT", "0.50", min_val=0.1, max_val=1.0),
            hard_stop_below_ema_pct=_env_float("EQUITY_HARD_STOP_PCT", "0.05", min_val=0.01, max_val=0.15),
            above_ema_bonus=_env_float("EQUITY_ABOVE_EMA_BONUS", "1.0", min_val=1.0, max_val=1.5),
        )

@dataclass(frozen=True)
class PortfolioHeatConfig:
    max_portfolio_heat_pct: float = 0.06
    max_same_direction_heat_pct: float = 0.04
    correlated_pair_max_heat_pct: float = 0.03

    @staticmethod
    def from_env() -> PortfolioHeatConfig:
        return PortfolioHeatConfig(
            max_portfolio_heat_pct=_env_float("MAX_PORTFOLIO_HEAT_PCT", "0.06", min_val=0.02, max_val=0.15),
            max_same_direction_heat_pct=_env_float("MAX_SAME_DIR_HEAT_PCT", "0.04", min_val=0.01, max_val=0.10),
            correlated_pair_max_heat_pct=_env_float("CORRELATED_HEAT_PCT", "0.03", min_val=0.01, max_val=0.08),
        )

@dataclass(frozen=True)
class ProfitProtectionConfig:
    enabled: bool = True
    profit_lock_ratio: float = 0.50
    min_profit_to_activate_pct: float = 0.05
    daily_profit_target_pct: float = 0.0
    weekly_profit_target_pct: float = 0.0

    @staticmethod
    def from_env() -> ProfitProtectionConfig:
        return ProfitProtectionConfig(
            enabled=_getenv_bool("PROFIT_PROTECTION_ENABLED", "true"),
            profit_lock_ratio=_env_float("PROFIT_LOCK_RATIO", "0.50", min_val=0.1, max_val=0.9),
            min_profit_to_activate_pct=_env_float("MIN_PROFIT_TO_ACTIVATE_PCT", "0.05", min_val=0.01, max_val=0.20),
            daily_profit_target_pct=_env_float("DAILY_PROFIT_TARGET_PCT", "0", min_val=0, max_val=0.20),
            weekly_profit_target_pct=_env_float("WEEKLY_PROFIT_TARGET_PCT", "0", min_val=0, max_val=0.30),
        )

@dataclass(frozen=True)
class DynamicLeverageConfig:
    enabled: bool = True
    calm_max_leverage: int = 10
    normal_max_leverage: int = 5
    volatile_max_leverage: int = 3
    crisis_max_leverage: int = 1
    drawdown_leverage_reduction: bool = True

    @staticmethod
    def from_env() -> DynamicLeverageConfig:
        return DynamicLeverageConfig(
            enabled=_getenv_bool("DYNAMIC_LEVERAGE_ENABLED", "true"),
            calm_max_leverage=_env_int("CALM_MAX_LEVERAGE", "10", min_val=1, max_val=50),
            normal_max_leverage=_env_int("NORMAL_MAX_LEVERAGE", "5", min_val=1, max_val=30),
            volatile_max_leverage=_env_int("VOLATILE_MAX_LEVERAGE", "3", min_val=1, max_val=20),
            crisis_max_leverage=_env_int("CRISIS_MAX_LEVERAGE", "1", min_val=1, max_val=5),
            drawdown_leverage_reduction=_getenv_bool("DRAWDOWN_LEVERAGE_REDUCTION", "true"),
        )


@dataclass
class BotConfig:
    telegram_token:   str = os.getenv("TELEGRAM_TOKEN",   "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
    primary_timeframe:     str = os.getenv("PRIMARY_TIMEFRAME", "Min15")
    htf_timeframe:         str = os.getenv("HTF_TIMEFRAME",     "Min60")
    kline_limit:           int = int(os.getenv("KLINE_LIMIT",     "260"))
    htf_kline_limit:       int = int(os.getenv("HTF_KLINE_LIMIT", "260"))

    symbols: List[str] = field(
        default_factory=lambda: os.getenv("SYMBOLS", "XAUT_USDT,NAS100_USDT").split(",")
    )

    starting_balance:       float = float(os.getenv("STARTING_BALANCE",    "1000"))
    leverage:               int   = int(os.getenv("LEVERAGE",              "5"))
    risk_per_trade:         float = float(os.getenv("RISK_PER_TRADE",      "0.01"))
    min_stop_distance_pct:  float = float(os.getenv("MIN_STOP_DISTANCE_PCT", "0.0008"))
    daily_loss_limit_pct:   float = float(os.getenv("DAILY_LOSS_LIMIT_PCT","0.08"))
    max_consecutive_losses: int   = int(os.getenv("MAX_CONSECUTIVE_LOSSES","3"))
    max_open_positions:     int   = int(os.getenv("MAX_OPEN_POSITIONS",    "1"))
    max_trades_per_day:     int   = int(os.getenv("MAX_TRADES_PER_DAY",    "12"))
    cooldown_minutes:       int   = int(os.getenv("COOLDOWN_MINUTES",      "10"))

    fee_rate:               float = float(os.getenv("FEE_RATE",            "0.0004"))
    slippage_rate:          float = float(os.getenv("SLIPPAGE_RATE",       "0.0003"))

    breakout_lookback:       int   = int(os.getenv("BREAKOUT_LOOKBACK",     "20"))
    atr_period:              int   = int(os.getenv("ATR_PERIOD",            "14"))
    atr_stop_mult:           float = float(os.getenv("ATR_STOP_MULT",       "1.4"))
    rr_ratio:                float = float(os.getenv("RR_RATIO",            "2.2"))
    trailing_activation_r:   float = float(os.getenv("TRAILING_ACTIVATION_R","1.15"))
    trailing_gap_pct:        float = float(os.getenv("TRAILING_GAP_PCT",    "0.008"))
    break_even_r:            float = float(os.getenv("BREAK_EVEN_R",        "0.85"))
    partial_tp_r:            float = float(os.getenv("PARTIAL_TP_R",        "1.3"))
    partial_close_ratio:     float = float(os.getenv("PARTIAL_CLOSE_RATIO", "0.35"))
    secondary_partial_tp_r:          float = float(os.getenv("SECONDARY_PARTIAL_TP_R",          "1.8"))
    secondary_partial_close_ratio:   float = float(os.getenv("SECONDARY_PARTIAL_CLOSE_RATIO",   "0.25"))
    time_stop_minutes:       int   = int(os.getenv("TIME_STOP_MINUTES",     "180"))

    aggressive_score_threshold: int   = int(os.getenv("AGGRESSIVE_SCORE_THRESHOLD", "4"))
    calm_score_threshold:       int   = int(os.getenv("CALM_SCORE_THRESHOLD",       "3"))
    confidence_min_aggressive:  int   = int(os.getenv("CONFIDENCE_MIN_AGGRESSIVE",  "55"))
    confidence_min_calm:        int   = int(os.getenv("CONFIDENCE_MIN_CALM",        "58"))
    risk_mode:                  str   = os.getenv("RISK_MODE", "aggressive").lower()

    funding_abs_limit:      float = float(os.getenv("FUNDING_ABS_LIMIT",   "0.0025"))
    max_last_candle_pct:    float = float(os.getenv("MAX_LAST_CANDLE_PCT",  "0.025"))
    max_spread_pct:         float = float(os.getenv("MAX_SPREAD_PCT",       "0.0025"))
    adx_trend_threshold:    float = float(os.getenv("ADX_TREND_THRESHOLD",  "18"))
    vwap_distance_limit:    float = float(os.getenv("VWAP_DISTANCE_LIMIT",  "0.012"))
    volatile_atr_ratio:     float = float(os.getenv("VOLATILE_ATR_RATIO",   "0.013"))
    require_trending_regime: bool = _getenv_bool("REQUIRE_TRENDING_REGIME", "false")

    ema_distance_threshold:         float = float(os.getenv("EMA_DISTANCE_THRESHOLD",         "0.0018"))
    sr_lookback:                    int   = int(os.getenv("SR_LOOKBACK",                    "48"))
    sr_atr_tolerance:               float = float(os.getenv("SR_ATR_TOLERANCE",               "0.65"))
    rsi_divergence_lookback:        int   = int(os.getenv("RSI_DIVERGENCE_LOOKBACK",        "8"))
    rsi_divergence_min_delta:       float = float(os.getenv("RSI_DIVERGENCE_MIN_DELTA",       "4.0"))
    preferred_session_confidence_bonus: int = int(os.getenv("PREFERRED_SESSION_CONFIDENCE_BONUS", "5"))
    opposite_signal_confidence_min: int   = int(os.getenv("OPPOSITE_SIGNAL_CONFIDENCE_MIN", "65"))
    profitable_time_stop_extension: float = float(os.getenv("PROFITABLE_TIME_STOP_EXTENSION","1.5"))

    confidence_size_boost_threshold:  int   = int(os.getenv("CONFIDENCE_SIZE_BOOST_THRESHOLD",  "80"))
    confidence_size_reduce_threshold: int   = int(os.getenv("CONFIDENCE_SIZE_REDUCE_THRESHOLD", "50"))
    confidence_size_boost_multiplier:  float = float(os.getenv("CONFIDENCE_SIZE_BOOST_MULTIPLIER",  "1.1"))
    confidence_size_reduce_multiplier: float = float(os.getenv("CONFIDENCE_SIZE_REDUCE_MULTIPLIER", "0.7"))

    use_session_filter:     bool  = _getenv_bool("USE_SESSION_FILTER",  "true")
    xaut_session_utc:       str   = os.getenv("XAUT_SESSION_UTC",       "05-22")
    nas100_session_utc:     str   = os.getenv("NAS100_SESSION_UTC",     "12-21")
    session_max_trades:     int   = int(os.getenv("SESSION_MAX_TRADES", "10"))
    xaut_preferred_hours:   str   = os.getenv("XAUT_PREFERRED_HOURS",   "07-11,13-17")
    nas100_preferred_hours: str   = os.getenv("NAS100_PREFERRED_HOURS", "13-17,18-20")

    use_news_filter:            bool = _getenv_bool("USE_NEWS_FILTER",   "false")
    news_blackout_hours_utc:    str  = os.getenv("NEWS_BLACKOUT_HOURS_UTC", "13,14")

    backtest_default_limit: int = int(os.getenv("BACKTEST_DEFAULT_LIMIT", "600"))
    backtest_min_bars:      int = int(os.getenv("BACKTEST_MIN_BARS",      "120"))
    backtest_max_hold_bars: int = int(os.getenv("BACKTEST_MAX_HOLD_BARS", "24"))
    backtest_wf_splits:     int = int(os.getenv("BACKTEST_WF_SPLITS",     "3"))

    # NAS100 Asia Range model
    use_nas100_asia_model:        bool  = _getenv_bool("USE_NAS100_ASIA_MODEL", "true")
    ny_timezone:                  str   = os.getenv("NY_TIMEZONE",                  "America/New_York")
    nas100_model_timeframe:       str   = os.getenv("NAS100_MODEL_TIMEFRAME",       "Min5")
    nas100_model_kline_limit:     int   = int(os.getenv("NAS100_MODEL_KLINE_LIMIT", "720"))
    asia_range_ny:                str   = os.getenv("ASIA_RANGE_NY",                "20:00-03:00")
    nas100_preopen_window_ny:     str   = os.getenv("NAS100_PREOPEN_WINDOW_NY",     "08:00-09:29")
    nas100_open_window_ny:        str   = os.getenv("NAS100_OPEN_WINDOW_NY",        "09:30-09:50")
    nas100_macro_windows_ny:      str   = os.getenv("NAS100_MACRO_WINDOWS_NY",      "09:50-10:10,10:50-11:00,11:10-11:30,11:50-12:00")
    asia_range_max_width_atr:     float = float(os.getenv("ASIA_RANGE_MAX_WIDTH_ATR",    "6.5"))
    asia_range_max_drift_ratio:   float = float(os.getenv("ASIA_RANGE_MAX_DRIFT_RATIO",  "0.55"))
    asia_sweep_min_atr:           float = float(os.getenv("ASIA_SWEEP_MIN_ATR",          "0.12"))
    cisd_displacement_atr:        float = float(os.getenv("CISD_DISPLACEMENT_ATR",       "0.45"))
    fvg_eq_tolerance_atr:         float = float(os.getenv("FVG_EQ_TOLERANCE_ATR",        "0.18"))
    asia_model_confidence_floor:  int   = int(os.getenv("ASIA_MODEL_CONFIDENCE_FLOOR",   "60"))

    # NEW: XAUT London Open Range model
    # XAUT için de Min5 LTF kullanılır — aynı timeframe ayarı NAS100 ile paylaşılır
    # Ayrı bir limit tanımlayabilirsiniz:
    xaut_ltf_timeframe:           str   = os.getenv("XAUT_LTF_TIMEFRAME",           "Min5")
    xaut_ltf_kline_limit:         int   = int(os.getenv("XAUT_LTF_KLINE_LIMIT",     "360"))
    # London saatleri config'e eklendi — gerekirse değiştirebilirsiniz
    xaut_london_range_window:     str   = os.getenv("XAUT_LONDON_RANGE_WINDOW",     "07:00-08:00")
    xaut_london_trade_window:     str   = os.getenv("XAUT_LONDON_TRADE_WINDOW",     "08:00-09:30")

    dynamic_limits_enabled: bool = _getenv_bool("DYNAMIC_LIMITS_ENABLED", "true")
    vol_regime_low_atr_pct:      float = float(os.getenv("VOL_REGIME_LOW_ATR_PCT",      "0.006"))
    vol_regime_medium_atr_pct:   float = float(os.getenv("VOL_REGIME_MEDIUM_ATR_PCT",   "0.012"))
    vol_regime_high_atr_pct:     float = float(os.getenv("VOL_REGIME_HIGH_ATR_PCT",     "0.02"))

    risk_mult_low_vol:           float = float(os.getenv("RISK_MULT_LOW_VOL",           "1.00"))
    risk_mult_medium_vol:        float = float(os.getenv("RISK_MULT_MEDIUM_VOL",        "0.85"))
    risk_mult_high_vol:          float = float(os.getenv("RISK_MULT_HIGH_VOL",          "0.60"))
    risk_mult_extreme_vol:       float = float(os.getenv("RISK_MULT_EXTREME_VOL",       "0.35"))

    leverage_mult_low_vol:       float = float(os.getenv("LEVERAGE_MULT_LOW_VOL",       "1.00"))
    leverage_mult_medium_vol:    float = float(os.getenv("LEVERAGE_MULT_MEDIUM_VOL",    "0.80"))
    leverage_mult_high_vol:      float = float(os.getenv("LEVERAGE_MULT_HIGH_VOL",      "0.60"))
    leverage_mult_extreme_vol:   float = float(os.getenv("LEVERAGE_MULT_EXTREME_VOL",   "0.40"))

    spread_mult_low_vol:         float = float(os.getenv("SPREAD_MULT_LOW_VOL",         "1.00"))
    spread_mult_medium_vol:      float = float(os.getenv("SPREAD_MULT_MEDIUM_VOL",      "0.90"))
    spread_mult_high_vol:        float = float(os.getenv("SPREAD_MULT_HIGH_VOL",        "0.75"))
    spread_mult_extreme_vol:     float = float(os.getenv("SPREAD_MULT_EXTREME_VOL",     "0.50"))

    trades_per_day_mult_low_vol:       float = float(os.getenv("TRADES_PER_DAY_MULT_LOW_VOL",       "1.00"))
    trades_per_day_mult_medium_vol:    float = float(os.getenv("TRADES_PER_DAY_MULT_MEDIUM_VOL",    "0.85"))
    trades_per_day_mult_high_vol:      float = float(os.getenv("TRADES_PER_DAY_MULT_HIGH_VOL",      "0.60"))
    trades_per_day_mult_extreme_vol:   float = float(os.getenv("TRADES_PER_DAY_MULT_EXTREME_VOL",   "0.40"))

    cooldown_mult_low_vol:       float = float(os.getenv("COOLDOWN_MULT_LOW_VOL",       "1.00"))
    cooldown_mult_medium_vol:    float = float(os.getenv("COOLDOWN_MULT_MEDIUM_VOL",    "1.25"))
    cooldown_mult_high_vol:      float = float(os.getenv("COOLDOWN_MULT_HIGH_VOL",      "1.75"))
    cooldown_mult_extreme_vol:   float = float(os.getenv("COOLDOWN_MULT_EXTREME_VOL",   "2.50"))

    stop_mult_low_vol:           float = float(os.getenv("STOP_MULT_LOW_VOL",           "1.00"))
    stop_mult_medium_vol:        float = float(os.getenv("STOP_MULT_MEDIUM_VOL",        "1.10"))
    stop_mult_high_vol:          float = float(os.getenv("STOP_MULT_HIGH_VOL",          "1.25"))
    stop_mult_extreme_vol:       float = float(os.getenv("STOP_MULT_EXTREME_VOL",       "1.50"))

    disable_trading_extreme_vol: bool  = _getenv_bool("DISABLE_TRADING_EXTREME_VOL", "true")

    state_path:  str  = os.getenv("STATE_PATH",  "storage/state.json")
    wallet_path: str  = os.getenv("WALLET_PATH", "storage/wallet.json")
    trades_path: str  = os.getenv("TRADES_PATH", "storage/trades.json")
    log_path:    str  = os.getenv("LOG_PATH",    "storage/logs.txt")

    bot_enabled: bool = _getenv_bool("BOT_ENABLED", "true")
    sim_mode:    bool = _getenv_bool("SIM_MODE",    "true")

    # YENİ KURUMSAL RİSK KATMANLARI
    drawdown:       DrawdownProtectionConfig = field(default_factory=DrawdownProtectionConfig.from_env)
    kelly:          KellyCriterionConfig     = field(default_factory=KellyCriterionConfig.from_env)
    equity_curve:   EquityCurveConfig        = field(default_factory=EquityCurveConfig.from_env)
    portfolio_heat: PortfolioHeatConfig      = field(default_factory=PortfolioHeatConfig.from_env)
    profit_protection: ProfitProtectionConfig = field(default_factory=ProfitProtectionConfig.from_env)
    dynamic_leverage:  DynamicLeverageConfig  = field(default_factory=DynamicLeverageConfig.from_env)

    def mode_threshold(self) -> int:
        return self.aggressive_score_threshold if self.risk_mode == "aggressive" else self.calm_score_threshold

    def mode_confidence_min(self) -> int:
        return self.confidence_min_aggressive if self.risk_mode == "aggressive" else self.confidence_min_calm


CONFIG = BotConfig()
