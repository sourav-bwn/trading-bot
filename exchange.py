import ccxt
import pandas as pd
import logging
from config import (
    BINANCE_API_KEY,
    BINANCE_SECRET,
    SYMBOL,
    TIMEFRAME,
    CANDLE_LIMIT,
    DRY_RUN,
)

logger = logging.getLogger(__name__)


class Exchange:
    def __init__(self):
        self.exchange = ccxt.binance(
            {
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_SECRET,
                "sandbox": True,  # Enable testnet
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        self.exchange.load_markets()
        logger.info(
            f"Connected to Binance Testnet | Sandbox mode: {self.exchange.sandbox}"
        )

    def get_ohlcv(self, symbol=None, timeframe=None, limit=None):
        symbol = symbol or SYMBOL
        timeframe = timeframe or TIMEFRAME
        limit = limit or CANDLE_LIMIT
        raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def get_price(self, symbol=None):
        symbol = symbol or SYMBOL
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker["last"]

    def get_balance(self, currency="USDT"):
        balance = self.exchange.fetch_balance()
        return {
            "free": balance[currency]["free"] if currency in balance else 0.0,
            "used": balance[currency]["used"] if currency in balance else 0.0,
            "total": balance[currency]["total"] if currency in balance else 0.0,
        }

    def get_open_orders(self, symbol=None):
        symbol = symbol or SYMBOL
        return self.exchange.fetch_open_orders(symbol)

    def place_market_buy(self, symbol=None, amount_usdt=None):
        symbol = symbol or SYMBOL
        if DRY_RUN:
            price = self.get_price(symbol)
            qty = amount_usdt / price
            logger.info(
                f"[DRY RUN] Market BUY {symbol} | qty={qty:.6f} @ ${price:,.2f}"
            )
            return {
                "id": "dry_run",
                "symbol": symbol,
                "side": "buy",
                "amount": qty,
                "price": price,
                "cost": amount_usdt,
            }
        order = self.exchange.create_market_buy_order(
            symbol, None, params={"quoteOrderQty": amount_usdt}
        )
        logger.info(
            f"Market BUY {symbol} | {order['id']} | cost=${order.get('cost', 0):.2f}"
        )
        return order

    def place_market_sell(self, symbol=None, amount=None):
        symbol = symbol or SYMBOL
        if DRY_RUN:
            price = self.get_price(symbol)
            logger.info(
                f"[DRY RUN] Market SELL {symbol} | qty={amount:.6f} @ ${price:,.2f}"
            )
            return {
                "id": "dry_run",
                "symbol": symbol,
                "side": "sell",
                "amount": amount,
                "price": price,
                "cost": amount * price,
            }
        order = self.exchange.create_market_sell_order(symbol, amount)
        logger.info(f"Market SELL {symbol} | {order['id']} | amount={amount:.6f}")
        return order

    def get_base_balance(self, symbol=None):
        symbol = symbol or SYMBOL
        base = symbol.split("/")[0]
        return self.get_balance(base)
