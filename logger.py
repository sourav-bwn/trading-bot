import csv
import os
from datetime import datetime

from config import LOG_FILE


HEADERS = [
    "timestamp",
    "symbol",
    "side",
    "amount",
    "price",
    "cost",
    "pnl",
    "balance_usdt",
]


def init_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)


def log_trade(symbol, side, amount, price, cost, pnl=0.0, balance_usdt=0.0):
    init_log()
    row = [
        datetime.utcnow().isoformat(),
        symbol,
        side,
        f"{amount:.8f}",
        f"{price:.2f}",
        f"{cost:.2f}",
        f"{pnl:.2f}",
        f"{balance_usdt:.2f}",
    ]
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def get_trades():
    init_log()
    trades = []
    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)
    return trades


def get_performance():
    trades = get_trades()
    if not trades:
        return {"total_trades": 0, "total_pnl": 0.0, "win_rate": 0.0}

    # Tolerate older logs written with thousands separators.
    pnls = [float(str(t["pnl"]).replace(",", "")) for t in trades]
    wins = [p for p in pnls if p > 0]
    return {
        "total_trades": len(pnls),
        "total_pnl": sum(pnls),
        "win_rate": len(wins) / len(pnls) * 100 if pnls else 0,
        "avg_pnl": sum(pnls) / len(pnls) if pnls else 0,
    }
