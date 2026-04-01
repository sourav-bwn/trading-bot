# Crypto Trading Bot

A paper trading bot for cryptocurrency using Binance Testnet. Built with Python, CCXT, and a simple Moving Average + RSI strategy.

> **WARNING**: This is for educational purposes. Paper trading only by default. Do not use real money until you fully understand the risks. Most traders lose money.

## Features

- Paper trading on Binance Testnet (free, no real money)
- Moving Average Crossover + RSI strategy
- Stop-loss and take-profit risk management
- Backtesting against historical data
- Trade logging to CSV
- Configurable parameters

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Binance Testnet API keys

1. Go to https://testnet.binance.vision/
2. Generate API Key and Secret
3. Export them as environment variables:

```bash
export BINANCE_API_KEY="your_testnet_api_key"
export BINANCE_SECRET="your_testnet_secret"
```

### 3. Run the bot

```bash
python bot.py
```

### 4. Run a backtest

```bash
python backtest.py
```

## Configuration

Edit `config.py` to customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SYMBOL` | BTC/USDT | Trading pair |
| `TIMEFRAME` | 1h | Candle interval |
| `SMA_SHORT` | 20 | Short moving average period |
| `SMA_LONG` | 50 | Long moving average period |
| `RSI_PERIOD` | 14 | RSI calculation period |
| `POSITION_SIZE` | 0.10 | 10% of balance per trade |
| `STOP_LOSS_PCT` | 0.03 | 3% stop loss |
| `TAKE_PROFIT_PCT` | 0.05 | 5% take profit |
| `DRY_RUN` | True | Paper trading mode |

## Strategy

The bot uses a simple strategy:

- **BUY**: When SMA(20) crosses above SMA(50) AND RSI < 70
- **SELL**: When SMA(20) crosses below SMA(50) OR RSI > 70
- **STOP LOSS**: -3% from entry price
- **TAKE PROFIT**: +5% from entry price

## File Structure

```
trading-bot/
├── bot.py           # Main trading loop
├── config.py        # Configuration and parameters
├── exchange.py      # CCXT exchange wrapper
├── strategy.py      # Trading strategy logic
├── backtest.py      # Backtesting engine
├── logger.py        # Trade logging to CSV
├── requirements.txt # Python dependencies
└── README.md
```

## Disclaimer

This software is for educational purposes only. Trading cryptocurrency carries significant risk. You may lose all invested capital. Never trade with money you cannot afford to lose.
