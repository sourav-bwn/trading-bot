import pandas as pd
import numpy as np
from config import SMA_SHORT, SMA_LONG, RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD


def calculate_sma(df, period):
    return df["close"].rolling(window=period).mean()


def calculate_rsi(df, period=RSI_PERIOD):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def add_indicators(df, sma_short=SMA_SHORT, sma_long=SMA_LONG, rsi_period=RSI_PERIOD):
    df = df.copy()
    df["sma_short"] = calculate_sma(df, sma_short)
    df["sma_long"] = calculate_sma(df, sma_long)
    df["rsi"] = calculate_rsi(df, rsi_period)
    return df.dropna()


def get_signal(
    df,
    sma_short=SMA_SHORT,
    sma_long=SMA_LONG,
    rsi_ob=RSI_OVERBOUGHT,
    rsi_os=RSI_OVERSOLD,
):
    df = add_indicators(df, sma_short, sma_long)
    if len(df) < 2:
        return "HOLD", {}

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    sma_cross_up = (
        prev["sma_short"] <= prev["sma_long"] and curr["sma_short"] > curr["sma_long"]
    )
    sma_cross_down = (
        prev["sma_short"] >= prev["sma_long"] and curr["sma_short"] < curr["sma_long"]
    )

    info = {
        "price": curr["close"],
        "sma_short": curr["sma_short"],
        "sma_long": curr["sma_long"],
        "rsi": curr["rsi"],
    }

    if sma_cross_up and curr["rsi"] < rsi_ob:
        return "BUY", info
    elif sma_cross_down or curr["rsi"] > rsi_ob:
        return "SELL", info
    else:
        return "HOLD", info
