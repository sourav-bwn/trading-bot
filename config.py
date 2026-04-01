import os

# Binance Testnet API credentials
# Get yours at: https://testnet.binance.vision/
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

# Trading settings
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
CANDLE_LIMIT = 200

# Strategy parameters
SMA_SHORT = 20
SMA_LONG = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Risk management
POSITION_SIZE = 0.10  # 10% of base balance per trade
STOP_LOSS_PCT = 0.03  # 3% stop loss
TAKE_PROFIT_PCT = 0.05  # 5% take profit
MAX_OPEN_POSITIONS = 1

# Bot settings
LOOP_INTERVAL = 60  # seconds between iterations
DRY_RUN = True  # Paper trading mode (no real orders)

# Logging
LOG_FILE = "trades.csv"
LOG_LEVEL = "INFO"
