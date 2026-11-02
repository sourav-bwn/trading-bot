import logging
import math
import signal
import sys
import time
from datetime import datetime

from config import (
    SYMBOL,
    LOOP_INTERVAL,
    POSITION_SIZE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    MAX_OPEN_POSITIONS,
    DRY_RUN,
    LOG_LEVEL,
)
from exchange import Exchange
from strategy import get_signal
from logger import log_trade, get_performance, init_log, get_trades

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

running = True
position = None  # {"entry_price": float, "amount": float, "side": "buy"}
untracked_holdings = False  # real balance that cannot be reconciled with the trade log; blocks new buys


def shutdown(signum, frame):
    global running
    logger.info("Shutdown signal received. Exiting gracefully...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def check_stop_loss_take_profit(price):
    global position
    if position is None:
        return None
    entry = position["entry_price"]
    change = (price - entry) / entry
    if change <= -STOP_LOSS_PCT:
        logger.warning(
            f"STOP LOSS hit | entry=${entry:,.2f} now=${price:,.2f} ({change:.2%})"
        )
        return "stop_loss"
    if change >= TAKE_PROFIT_PCT:
        logger.info(
            f"TAKE PROFIT hit | entry=${entry:,.2f} now=${price:,.2f} ({change:.2%})"
        )
        return "take_profit"
    return None


def execute_buy(exchange):
    global position
    if untracked_holdings:
        logger.warning(
            "BUY blocked: exchange holdings found after restart that are not in the "
            "trade log. Reconcile them (sell manually or add the missing BUY row) "
            "before buying on top of them."
        )
        return
    if position is not None:
        logger.info("Already in position. Skipping BUY.")
        return

    balance = exchange.get_balance("USDT")
    trade_amount = balance["free"] * POSITION_SIZE
    if trade_amount < 10:
        logger.warning(f"Insufficient balance: ${balance['free']:,.2f} USDT")
        return

    order = exchange.place_market_buy(SYMBOL, trade_amount)
    price = order.get("price", exchange.get_price(SYMBOL))
    amount = order.get("amount", trade_amount / price)
    cost = order.get("cost", trade_amount)

    position = {"entry_price": price, "amount": amount, "side": "buy"}
    log_trade(
        SYMBOL, "BUY", amount, price, cost, pnl=0.0, balance_usdt=balance["free"] - cost
    )
    logger.info(f"BUY executed | {amount:.6f} @ ${price:,.2f} | cost=${cost:,.2f}")


def execute_sell(exchange, reason="signal"):
    global position
    if position is None:
        return

    order = exchange.place_market_sell(SYMBOL, position["amount"])
    price = order.get("price", exchange.get_price(SYMBOL))
    cost = order.get("cost", position["amount"] * price)
    pnl = (price - position["entry_price"]) * position["amount"]
    balance = exchange.get_balance("USDT")

    log_trade(
        SYMBOL,
        "SELL",
        position["amount"],
        price,
        cost,
        pnl=pnl,
        balance_usdt=balance["free"],
    )
    logger.info(
        f"SELL executed ({reason}) | {position['amount']:.6f} @ ${price:,.2f} | PnL=${pnl:+,.2f}"
    )
    position = None


def print_status(exchange, signal_name, info):
    balance_usdt = exchange.get_balance("USDT")
    balance_btc = exchange.get_balance("BTC")
    perf = get_performance()
    pos_str = f"${position['entry_price']:,.2f}" if position else "None"

    logger.info(
        f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
        f"Price=${info.get('price', 0):,.2f} | "
        f"SMA({info.get('sma_short', 0):,.0f}/{info.get('sma_long', 0):,.0f}) | "
        f"RSI={info.get('rsi', 0):.1f} | "
        f"Signal={signal_name} | "
        f"Position={pos_str} | "
        f"USDT=${balance_usdt['free']:,.2f} BTC={balance_btc['free']:.6f} | "
        f"Trades={perf['total_trades']} PnL=${perf['total_pnl']:+,.2f}"
    )


def restore_position(exchange, symbol=SYMBOL):
    """Restore state after a restart from the persisted trade log.

    Entry price and amount come from the logged fill prices of executed
    orders, never from the current market price: a guessed entry would
    silently move the stop-loss/take-profit anchor. In DRY_RUN the paper
    position exists only in the log, so the log alone is authoritative and
    the exchange balance is not consulted. In live mode the amount is
    clamped to the actual exchange balance. Holdings that cannot be
    attributed to a logged open BUY are left untraded and block new buys
    until reconciled.
    """
    global position, untracked_holdings
    untracked_holdings = False
    base = symbol.split("/")[0]
    open_entry = None
    open_amount = 0.0
    invalid_open = False
    for row in get_trades():
        side = str(row.get("side", "")).upper()
        try:
            amount = float(str(row["amount"]).replace(",", ""))
            price = float(str(row["price"]).replace(",", ""))
        except (KeyError, ValueError):
            price = None
            amount = None
        if side == "BUY":
            # Never restore an invented or invalid cost basis.
            if (
                price is None
                or amount is None
                or not math.isfinite(price)
                or not math.isfinite(amount)
                or price <= 0
                or amount <= 0
            ):
                invalid_open = True
                open_entry = None
                open_amount = 0.0
            else:
                invalid_open = False
                open_entry = price
                open_amount = amount
        elif side == "SELL" and open_entry is not None and amount is not None:
            open_amount -= amount
            if open_amount <= 1e-12:
                open_entry = None
                open_amount = 0.0

    if (open_entry is None or open_amount <= 0) and invalid_open:
        logger.error(
            "Trade log has an open BUY with a missing or invalid fill price; "
            "refusing to restore an invalid position."
        )
        if not DRY_RUN:
            untracked_holdings = True
        return None

    if open_entry is not None and open_amount > 0:
        amount = open_amount
        if not DRY_RUN:
            balance = exchange.get_balance(base)
            amount = min(open_amount, balance["free"])
            if amount < open_amount:
                logger.warning(
                    f"Logged open amount {open_amount:.6f} {base} exceeds balance "
                    f"{balance['free']:.6f}; tracking the balance only."
                )
            if amount <= 0.0001:
                return None
        position = {"entry_price": open_entry, "amount": amount, "side": "buy"}
        logger.info(
            f"Restored open position: {amount:.6f} {base} @ ${open_entry:,.2f} (from trade log)"
        )
        return position

    if not DRY_RUN:
        holdings = exchange.get_balance(base)["free"]
        if holdings > 0.0001:
            untracked_holdings = True
            logger.warning(
                f"Found {holdings:.6f} {base} with no logged open BUY. Leaving it "
                "untraded and blocking new BUYs until it is reconciled."
            )
    return None


def run():
    global position

    logger.info("=" * 60)
    logger.info("Trading Bot Starting")
    logger.info(f"Symbol: {SYMBOL} | DRY_RUN: {DRY_RUN}")
    logger.info("=" * 60)

    init_log()
    exchange = Exchange()

    # Restore state from the trade log if the bot restarted
    restore_position(exchange)

    while running:
        try:
            df = exchange.get_ohlcv()
            signal_name, info = get_signal(df)

            # Check stop-loss / take-profit first
            if position:
                sl_tp = check_stop_loss_take_profit(info["price"])
                if sl_tp:
                    execute_sell(exchange, reason=sl_tp)

            # Execute strategy signal
            if signal_name == "BUY" and position is None:
                execute_buy(exchange)
            elif signal_name == "SELL" and position is not None:
                execute_sell(exchange, reason="signal")

            print_status(exchange, signal_name, info)
            time.sleep(LOOP_INTERVAL)

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(LOOP_INTERVAL)

    logger.info("Bot stopped.")


if __name__ == "__main__":
    run()
