import os

# =========================
# Genel
# =========================
BOT_NAME = "MEXC Futures Paper Bot"
PAPER_MODE = True
START_BALANCE = float(os.getenv("START_BALANCE", "1000"))
LEVERAGE = int(os.getenv("LEVERAGE", "5"))

# Sadece bunlar taransın
SYMBOLS = os.getenv("SYMBOLS", "XAUT_USDT,NAS100_USDT").split(",")

<<<<<<< HEAD
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
    primary_timeframe: str = os.getenv("PRIMARY_TIMEFRAME", "Min15")
    htf_timeframe: str = os.getenv("HTF_TIMEFRAME", "Min60")
    primary_limit: int = int(os.getenv("PRIMARY_LIMIT", "180"))
    htf_limit: int = int(os.getenv("HTF_LIMIT", "180"))
=======
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))
>>>>>>> 6a56521f62a913f472c7d729dcf97ff33da4d9ff

# =========================
# Risk
# =========================
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.03"))  # %3
DAILY_MAX_LOSS_PCT = float(os.getenv("DAILY_MAX_LOSS_PCT", "0.08"))  # %8
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "12"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "15"))

# =========================
# Timeframe
# =========================
PRIMARY_TIMEFRAME = os.getenv("PRIMARY_TIMEFRAME", "Min15")
HTF_TIMEFRAME = os.getenv("HTF_TIMEFRAME", "Min60")

PRIMARY_LIMIT = int(os.getenv("PRIMARY_LIMIT", "180"))
HTF_LIMIT = int(os.getenv("HTF_LIMIT", "180"))

# =========================
# Giriş / Çıkış
# =========================
SIGNAL_THRESHOLD_LONG = int(os.getenv("SIGNAL_THRESHOLD_LONG", "3"))
SIGNAL_THRESHOLD_SHORT = int(os.getenv("SIGNAL_THRESHOLD_SHORT", "-3"))

ATR_MULTIPLIER = float(os.getenv("ATR_MULTIPLIER", "1.4"))
RISK_REWARD = float(os.getenv("RISK_REWARD", "1.8"))

<<<<<<< HEAD
    volume_spike_threshold: float = float(os.getenv("VOLUME_SPIKE_THRESHOLD", "1.2"))
    fake_breakout_wick_ratio: float = float(os.getenv("FAKE_BREAKOUT_WICK_RATIO", "0.45"))
    max_last_candle_range_atr: float = float(os.getenv("MAX_LAST_CANDLE_RANGE_ATR", "2.2"))
    regime_adx_threshold: float = float(os.getenv("REGIME_ADX_THRESHOLD", "20"))
    regime_bb_width_threshold: float = float(os.getenv("REGIME_BB_WIDTH_THRESHOLD", "0.018"))

    state_path: str = os.getenv("STATE_PATH", "storage/state.json")
    wallet_path: str = os.getenv("WALLET_PATH", "storage/wallet.json")
    trades_path: str = os.getenv("TRADES_PATH", "storage/trades.json")
    log_path: str = os.getenv("LOG_PATH", "storage/logs.txt")
=======
TRAILING_ACTIVATION_R = float(os.getenv("TRAILING_ACTIVATION_R", "1.1"))
TRAILING_GAP_PCT = float(os.getenv("TRAILING_GAP_PCT", "0.008"))  # %0.8
>>>>>>> 6a56521f62a913f472c7d729dcf97ff33da4d9ff

# =========================
# İndikatörler
# =========================
EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))

VOLUME_LOOKBACK = int(os.getenv("VOLUME_LOOKBACK", "20"))
BREAKOUT_LOOKBACK = int(os.getenv("BREAKOUT_LOOKBACK", "20"))

# =========================
# Filtreler
# =========================
VOLUME_SPIKE_THRESHOLD = float(os.getenv("VOLUME_SPIKE_THRESHOLD", "1.2"))
FAKE_BREAKOUT_WICK_RATIO = float(os.getenv("FAKE_BREAKOUT_WICK_RATIO", "0.45"))
MAX_LAST_CANDLE_RANGE_ATR = float(os.getenv("MAX_LAST_CANDLE_RANGE_ATR", "2.2"))

# Regime Detection
REGIME_ADX_THRESHOLD = float(os.getenv("REGIME_ADX_THRESHOLD", "20"))
REGIME_BB_WIDTH_THRESHOLD = float(os.getenv("REGIME_BB_WIDTH_THRESHOLD", "0.018"))

# =========================
# Telegram
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
