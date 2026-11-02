"""Offline tests for the strategy, backtest and trade-log modules.

No exchange connection or API key is needed: Exchange/ccxt is only imported
inside backtest.py's __main__ block, and the tests feed synthetic candles.
"""
import csv
import os
import sys
import tempfile
import types
import unittest

import numpy as np
import pandas as pd

import logger as logmod
from backtest import backtest, print_results
from strategy import add_indicators, calculate_rsi, calculate_sma, get_signal


def make_df(closes):
    closes = [float(c) for c in closes]
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


# A decline, a cross-up entry, a sharp drop (stop loss), then a recovery rally.
SCENARIO = (
    [120 - i for i in range(20)]
    + [103, 106, 109]
    + [100, 95]
    + [100, 106, 112, 118, 124, 130, 137]
)


class TestIndicators(unittest.TestCase):
    def test_sma_matches_plain_mean(self):
        df = make_df(range(1, 11))
        sma = calculate_sma(df, 3)
        self.assertAlmostEqual(sma.iloc[-1], 9.0)
        self.assertTrue(sma.iloc[:2].isna().all())

    def test_rsi_is_100_when_every_candle_gains(self):
        rsi = calculate_rsi(make_df(range(1, 31)))
        self.assertAlmostEqual(rsi.iloc[-1], 100.0)

    def test_rsi_is_0_when_every_candle_falls(self):
        rsi = calculate_rsi(make_df(range(30, 0, -1)))
        self.assertAlmostEqual(rsi.iloc[-1], 0.0)

    def test_add_indicators_drops_warmup_rows(self):
        df = add_indicators(make_df(range(1, 81)))
        self.assertFalse(df.isna().any().any())
        self.assertEqual(len(df), 80 - 49)  # longest warmup is the 50-candle SMA


class TestSignal(unittest.TestCase):
    def test_hold_when_history_is_too_short(self):
        signal, info = get_signal(make_df([100, 101, 102]))
        self.assertEqual(signal, "HOLD")
        self.assertEqual(info, {})

    def test_buy_on_bullish_cross_with_rsi_below_overbought(self):
        # Long decline keeps RSI low; the final bar crosses SMA(2) above SMA(4).
        closes = [120 - i for i in range(25)] + [96, 99]
        signal, info = get_signal(make_df(closes), sma_short=2, sma_long=4)
        self.assertEqual(signal, "BUY")
        self.assertLess(info["rsi"], 70)
        self.assertEqual(info["price"], 99.0)

    def test_sell_when_rsi_is_overbought(self):
        closes = [100.0 + i * 0.1 for i in range(120)]  # steady rise, RSI pinned at 100
        signal, _ = get_signal(make_df(closes))
        self.assertEqual(signal, "SELL")


class TestBacktest(unittest.TestCase):
    def test_no_trades_returns_full_shape_and_prints(self):
        closes = [100.0 + i * 0.1 for i in range(120)]
        results, trades = backtest(make_df(closes))
        self.assertEqual(trades, [])
        self.assertEqual(results["trades"], 0)
        self.assertEqual(results["final_balance"], 1000.0)
        # Used to raise KeyError on the summary keys.
        print_results(results, trades)

    def test_stop_loss_closes_trade_near_threshold(self):
        results, trades = backtest(make_df(SCENARIO), sma_short=2, sma_long=4)
        sl = [t for t in trades if t["reason"] == "stop_loss"]
        self.assertEqual(len(sl), 1)
        self.assertLessEqual(sl[0]["change_pct"], -0.03)
        self.assertAlmostEqual(sl[0]["pnl"], sl[0]["change_pct"] * 99.4340, places=1)

    def test_max_drawdown_tracks_mid_run_dip_not_just_final_balance(self):
        # Take profit at +10% so the run finishes above its starting peak: the
        # old final-balance formula reported 0% drawdown here.
        results, trades = backtest(
            make_df(SCENARIO), sma_short=2, sma_long=4, take_profit=0.10
        )
        self.assertGreater(results["final_balance"], 1000.0)
        self.assertGreater(results["max_drawdown_pct"], 0.5)
        self.assertEqual(results["trades"], 2)
        self.assertEqual(results["winning_trades"], 1)
        self.assertEqual(results["losing_trades"], 1)

    def test_position_size_parameter_scales_trade_cost(self):
        results, trades = backtest(
            make_df(SCENARIO), sma_short=2, sma_long=4, position_size=0.20
        )
        sl = [t for t in trades if t["reason"] == "stop_loss"][0]
        # Double the position size doubles the loss on the same price path.
        self.assertAlmostEqual(sl["pnl"], -11.32, places=1)


class TestTradeLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = logmod.LOG_FILE
        logmod.LOG_FILE = os.path.join(self.tmp, "trades.csv")

    def tearDown(self):
        logmod.LOG_FILE = self.old

    def test_large_amounts_round_trip_without_crashing(self):
        # 67,500.50 used to be written with a comma and broke float() parsing.
        logmod.log_trade("BTC/USDT", "SELL", 0.01, 67500.50, 675.0, pnl=1500.25, balance_usdt=10000.0)
        perf = logmod.get_performance()
        self.assertAlmostEqual(perf["total_pnl"], 1500.25)
        self.assertEqual(perf["total_trades"], 1)
        with open(logmod.LOG_FILE) as f:
            self.assertNotIn("67,500", f.read())

    def test_legacy_comma_formatted_rows_still_parse(self):
        logmod.init_log()
        with open(logmod.LOG_FILE, "a", newline="") as f:
            csv.writer(f).writerow(
                ["2026-10-18T09:00:00", "BTC/USDT", "SELL", "0.01000000", "67,500.50", "675.00", "1,500.25", "10,000.00"]
            )
        self.assertAlmostEqual(logmod.get_performance()["total_pnl"], 1500.25)


class TestPerformanceStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = logmod.LOG_FILE
        logmod.LOG_FILE = os.path.join(self.tmp, "trades.csv")

    def tearDown(self):
        logmod.LOG_FILE = self.old

    def test_open_buy_rows_do_not_dilute_stats(self):
        logmod.log_trade("BTC/USDT", "BUY", 0.01, 67000.0, 670.0, pnl=0.0, balance_usdt=9330.0)
        logmod.log_trade("BTC/USDT", "SELL", 0.01, 69000.0, 690.0, pnl=20.0, balance_usdt=9350.0)
        perf = logmod.get_performance()
        self.assertEqual(perf["total_trades"], 1)
        self.assertAlmostEqual(perf["total_pnl"], 20.0)
        self.assertAlmostEqual(perf["win_rate"], 100.0)

    def test_only_buys_logged_yields_zero_stats(self):
        logmod.log_trade("BTC/USDT", "BUY", 0.01, 67000.0, 670.0, pnl=0.0, balance_usdt=9330.0)
        perf = logmod.get_performance()
        self.assertEqual(perf["total_trades"], 0)
        self.assertEqual(perf["total_pnl"], 0.0)


class TestRestorePosition(unittest.TestCase):
    """bot.py imports ccxt via exchange.py; stub that module so tests stay offline."""

    def setUp(self):
        self._fake = types.ModuleType("exchange")
        self._fake.Exchange = object
        self._saved = sys.modules.get("exchange")
        sys.modules["exchange"] = self._fake
        sys.modules.pop("bot", None)
        import bot
        self.bot = bot
        self.tmp = tempfile.mkdtemp()
        self.old_log = logmod.LOG_FILE
        logmod.LOG_FILE = os.path.join(self.tmp, "trades.csv")

    def tearDown(self):
        self.bot.position = None
        self.bot.untracked_holdings = False
        logmod.LOG_FILE = self.old_log
        sys.modules.pop("bot", None)
        if self._saved is not None:
            sys.modules["exchange"] = self._saved
        else:
            sys.modules.pop("exchange", None)

    def test_dry_run_restores_from_log_without_consulting_exchange(self):
        # Simulated rows are the paper position; exchange balance is unrelated.
        logmod.log_trade("BTC/USDT", "BUY", 0.01, 65000.0, 650.0, pnl=0.0, balance_usdt=9350.0)

        class FakeExchange:
            def get_balance(self, currency):
                raise AssertionError("dry-run restore must not read exchange holdings")

            def get_price(self, symbol):
                raise AssertionError("restore must not anchor on current market price")

        self.bot.position = None
        self.bot.DRY_RUN = True
        pos = self.bot.restore_position(FakeExchange())
        self.assertIsNotNone(pos)
        self.assertEqual(pos["entry_price"], 65000.0)
        self.assertEqual(pos["amount"], 0.01)

    def test_live_restore_clamps_amount_to_exchange_balance(self):
        logmod.log_trade("BTC/USDT", "BUY", 0.01, 65000.0, 650.0, pnl=0.0, balance_usdt=9350.0)

        class FakeExchange:
            def get_balance(self, currency):
                return {"free": 0.007, "used": 0.0, "total": 0.007}

            def get_price(self, symbol):
                raise AssertionError("restore must not anchor on current market price")

        self.bot.position = None
        old_dry = self.bot.DRY_RUN
        self.bot.DRY_RUN = False
        try:
            pos = self.bot.restore_position(FakeExchange())
        finally:
            self.bot.DRY_RUN = old_dry
        self.assertEqual(pos["amount"], 0.007)
        self.assertEqual(pos["entry_price"], 65000.0)

    def test_unlogged_holdings_block_new_buys(self):
        # A closed log plus real holdings: stay flat and refuse to stack a buy.
        logmod.log_trade("BTC/USDT", "BUY", 0.01, 65000.0, 650.0, pnl=0.0, balance_usdt=9350.0)
        logmod.log_trade("BTC/USDT", "SELL", 0.01, 66000.0, 660.0, pnl=10.0, balance_usdt=10010.0)

        class FakeExchange:
            def __init__(self):
                self.orders = []

            def get_balance(self, currency):
                if currency == "BTC":
                    return {"free": 0.005, "used": 0.0, "total": 0.005}
                return {"free": 10000.0, "used": 0.0, "total": 10000.0}

            def place_market_buy(self, symbol, amount_usdt):
                self.orders.append((symbol, amount_usdt))
                return {"id": "x", "price": 67000.0, "amount": 0.001, "cost": amount_usdt}

        exchange = FakeExchange()
        self.bot.position = None
        self.bot.untracked_holdings = False
        old_dry = self.bot.DRY_RUN
        self.bot.DRY_RUN = False
        try:
            with self.assertLogs("bot", level="WARNING"):
                self.assertIsNone(self.bot.restore_position(exchange))
            self.assertIsNone(self.bot.position)
            self.assertTrue(self.bot.untracked_holdings)
            self.bot.execute_buy(exchange)
            self.assertEqual(exchange.orders, [], "BUY must be blocked until holdings are reconciled")
            self.assertIsNone(self.bot.position)
        finally:
            self.bot.DRY_RUN = old_dry
            self.bot.untracked_holdings = False

    def test_invalid_logged_fill_price_is_refused_not_guessed(self):
        # A BUY row with a non-finite price must not become a position.
        logmod.init_log()
        with open(logmod.LOG_FILE, "a", newline="") as f:
            csv.writer(f).writerow(
                ["2026-11-02T09:00:00", "BTC/USDT", "BUY", "0.005", "nan", "325.00", "0.00", "9675.00"]
            )

        class FakeExchange:
            def get_balance(self, currency):
                return {"free": 0.005, "used": 0.0, "total": 0.005}

            def get_price(self, symbol):
                raise AssertionError("no price may be fetched to patch an invalid entry")

        self.bot.position = None
        old_dry = self.bot.DRY_RUN
        self.bot.DRY_RUN = False
        try:
            self.assertIsNone(self.bot.restore_position(FakeExchange()))
            self.assertIsNone(self.bot.position)
            self.assertTrue(self.bot.untracked_holdings)
        finally:
            self.bot.DRY_RUN = old_dry
            self.bot.untracked_holdings = False

    def test_reconciled_log_clears_the_buy_block(self):
        # Once the log matches the holdings, restore works and buys are allowed.
        logmod.log_trade("BTC/USDT", "BUY", 0.005, 65000.0, 325.0, pnl=0.0, balance_usdt=9675.0)

        class FakeExchange:
            def get_balance(self, currency):
                return {"free": 0.005, "used": 0.0, "total": 0.005}

        self.bot.position = None
        old_dry = self.bot.DRY_RUN
        self.bot.DRY_RUN = False
        try:
            pos = self.bot.restore_position(FakeExchange())
        finally:
            self.bot.DRY_RUN = old_dry
        self.assertIsNotNone(pos)
        self.assertFalse(self.bot.untracked_holdings)


if __name__ == "__main__":
    unittest.main()
