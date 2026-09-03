"""Pure technical indicators operating on validated OHLCV data."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.validation import validate_ohlcv


@dataclass(frozen=True)
class MacdParameters:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    def __post_init__(self) -> None:
        if not 0 < self.fast_period < self.slow_period or self.signal_period <= 0:
            raise ValueError("MACD periods must be positive and fast_period less than slow_period")


def exponential_moving_average(values: pd.Series, period: int) -> pd.Series:
    """Calculate an EMA, leaving values undefined until enough history exists."""
    _validate_period(period)
    return values.ewm(span=period, adjust=False, min_periods=period).mean()


def relative_strength_index(closes: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Wilder's RSI, preserving undefined warm-up values."""
    _validate_period(period)
    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rsi = 100 - (100 / (1 + average_gain / average_loss))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100.0)
    rsi = rsi.mask((average_gain == 0) & (average_loss > 0), 0.0)
    return rsi.mask((average_gain == 0) & (average_loss == 0), 50.0)


def average_true_range(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Wilder's ATR from OHLC data."""
    _validate_period(period)
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(closes: pd.Series, parameters: MacdParameters = MacdParameters()) -> pd.DataFrame:
    """Calculate MACD line, signal line, and histogram."""
    fast = exponential_moving_average(closes, parameters.fast_period)
    slow = exponential_moving_average(closes, parameters.slow_period)
    line = fast - slow
    signal = line.ewm(
        span=parameters.signal_period,
        adjust=False,
        min_periods=parameters.signal_period,
    ).mean()
    return pd.DataFrame({"macd": line, "macd_signal": signal, "macd_histogram": line - signal})


def recent_volatility(closes: pd.Series, period: int = 20) -> pd.Series:
    """Calculate rolling standard deviation of close-to-close percentage returns."""
    _validate_period(period)
    return closes.pct_change().rolling(window=period, min_periods=period).std(ddof=0)


def with_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the initial indicator set to validated OHLCV data."""
    result = validate_ohlcv(frame)
    result["ema_9"] = exponential_moving_average(result["close"], 9)
    result["ema_21"] = exponential_moving_average(result["close"], 21)
    result["rsi_14"] = relative_strength_index(result["close"], 14)
    result["atr_14"] = average_true_range(result, 14)
    result = result.join(macd(result["close"]))
    result["volatility_20"] = recent_volatility(result["close"], 20)
    return result


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be greater than zero")
