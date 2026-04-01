import sys
import logging
import pandas as pd
import numpy as np

from config import (
    SYMBOL,
    TIMEFRAME,
    SMA_SHORT,
    SMA_LONG,
    RSI_PERIOD,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)
from strategy import add_indicators, get_signal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fetch_historical(exchange_instance, symbol=None, timeframe=None, limit=1000):
    symbol = symbol or SYMBOL
    timeframe = timeframe or TIMEFRAME
    return exchange_instance.get_ohlcv(symbol, timeframe, limit=limit)


def backtest(
    df,
    sma_short=SMA_SHORT,
    sma_long=SMA_LONG,
    rsi_ob=RSI_OVERBOUGHT,
    rsi_os=RSI_OVERSOLD,
    stop_loss=STOP_LOSS_PCT,
    take_profit=TAKE_PROFIT_PCT,
):
    df = add_indicators(df, sma_short, sma_long, RSI_PERIOD)
    if len(df) < sma_long + 10:
        logger.error("Not enough data for backtest")
        return None

    trades = []
    position = None
    capital = 1000.0
    balance = capital
    peak_balance = capital

    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        sma_cross_up = (
            prev["sma_short"] <= prev["sma_long"]
            and curr["sma_short"] > curr["sma_long"]
        )
        sma_cross_down = (
            prev["sma_short"] >= prev["sma_long"]
            and curr["sma_short"] < curr["sma_long"]
        )

        # Check stop-loss / take-profit
        if position:
            change = (curr["close"] - position["entry"]) / position["entry"]
            if change <= -stop_loss or change >= take_profit:
                pnl = change * position["cost"]
                balance += pnl
                trades.append(
                    {
                        "entry_price": position["entry"],
                        "exit_price": curr["close"],
                        "pnl": pnl,
                        "reason": "stop_loss"
                        if change <= -stop_loss
                        else "take_profit",
                        "change_pct": change,
                    }
                )
                position = None
                continue

        # Signal logic
        if position is None and sma_cross_up and curr["rsi"] < rsi_ob:
            position = {"entry": curr["close"], "cost": balance * 0.10}
        elif position is not None and (sma_cross_down or curr["rsi"] > rsi_ob):
            change = (curr["close"] - position["entry"]) / position["entry"]
            pnl = change * position["cost"]
            balance += pnl
            trades.append(
                {
                    "entry_price": position["entry"],
                    "exit_price": curr["close"],
                    "pnl": pnl,
                    "reason": "signal",
                    "change_pct": change,
                }
            )
            position = None

        peak_balance = max(peak_balance, balance)

    # Close any open position at last price
    if position:
        last_price = df.iloc[-1]["close"]
        change = (last_price - position["entry"]) / position["entry"]
        pnl = change * position["cost"]
        balance += pnl
        trades.append(
            {
                "entry_price": position["entry"],
                "exit_price": last_price,
                "pnl": pnl,
                "reason": "end_of_data",
                "change_pct": change,
            }
        )

    if not trades:
        logger.info("No trades generated during backtest period.")
        return {
            "trades": 0,
            "pnl": 0,
            "return_pct": 0,
            "win_rate": 0,
            "max_drawdown": 0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    total_pnl = sum(pnls)
    max_dd = (peak_balance - balance) / peak_balance * 100 if peak_balance > 0 else 0

    results = {
        "trades": len(trades),
        "total_pnl": total_pnl,
        "return_pct": total_pnl / capital * 100,
        "win_rate": len(wins) / len(pnls) * 100,
        "avg_pnl": total_pnl / len(pnls),
        "max_drawdown_pct": max_dd,
        "final_balance": balance,
        "losing_trades": len([p for p in pnls if p <= 0]),
        "winning_trades": len(wins),
        "best_trade": max(pnls),
        "worst_trade": min(pnls),
    }

    return results, trades


def print_results(results, trades):
    if results is None:
        return

    logger.info("=" * 50)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 50)
    logger.info(f"Total trades:    {results['trades']}")
    logger.info(f"Winning trades:  {results['winning_trades']}")
    logger.info(f"Losing trades:   {results['losing_trades']}")
    logger.info(f"Win rate:        {results['win_rate']:.1f}%")
    logger.info(f"Total PnL:       ${results['total_pnl']:+,.2f}")
    logger.info(f"Return:          {results['return_pct']:+,.2f}%")
    logger.info(f"Avg PnL/trade:   ${results['avg_pnl']:+,.2f}")
    logger.info(f"Best trade:      ${results['best_trade']:+,.2f}")
    logger.info(f"Worst trade:     ${results['worst_trade']:+,.2f}")
    logger.info(f"Max drawdown:    {results['max_drawdown_pct']:.2f}%")
    logger.info(f"Final balance:   ${results['final_balance']:,.2f}")
    logger.info("=" * 50)

    if trades:
        logger.info("\nLast 5 trades:")
        for t in trades[-5:]:
            logger.info(
                f"  {t['reason']:12s} | "
                f"Entry=${t['entry_price']:,.2f} Exit=${t['exit_price']:,.2f} | "
                f"PnL=${t['pnl']:+,.2f} ({t['change_pct']:+.2%})"
            )


if __name__ == "__main__":
    from exchange import Exchange

    logger.info("Starting backtest...")
    exchange = Exchange()
    df = fetch_historical(exchange, limit=1000)
    logger.info(f"Fetched {len(df)} candles for {SYMBOL}")

    results = backtest(df)
    if results and isinstance(results, tuple):
        r, trades = results
        print_results(r, trades)
    else:
        print_results(results, [])
