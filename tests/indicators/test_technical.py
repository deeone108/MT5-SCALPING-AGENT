import numpy as np
import pandas as pd
import pytest

from mt5_scalping_agent.indicators import (
    MacdParameters,
    average_true_range,
    exponential_moving_average,
    macd,
    recent_volatility,
    relative_strength_index,
    with_indicators,
)


def ohlcv_frame(rows: int = 60) -> pd.DataFrame:
    close = pd.Series(np.linspace(1.0, 1.6, rows))
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC"),
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "tick_volume": 100,
        }
    )


def test_ema_observes_warmup_period() -> None:
    ema = exponential_moving_average(ohlcv_frame(12)["close"], 9)

    assert ema.iloc[:8].isna().all()
    assert ema.iloc[-1] > 1.0


def test_rsi_is_100_for_continuous_gains_after_warmup() -> None:
    rsi = relative_strength_index(ohlcv_frame(30)["close"], 14)

    assert rsi.iloc[:14].isna().all()
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_atr_is_positive_after_warmup() -> None:
    atr = average_true_range(ohlcv_frame(), 14)

    assert atr.iloc[:13].isna().all()
    assert atr.iloc[-1] > 0


def test_macd_validates_periods_and_returns_expected_columns() -> None:
    result = macd(ohlcv_frame()["close"])

    assert list(result.columns) == ["macd", "macd_signal", "macd_histogram"]
    with pytest.raises(ValueError, match="fast_period"):
        MacdParameters(fast_period=26, slow_period=12)


def test_volatility_and_indicator_frame() -> None:
    frame = ohlcv_frame()
    volatility = recent_volatility(frame["close"], 20)
    result = with_indicators(frame)

    assert volatility.iloc[:20].isna().all()
    assert {"ema_9", "ema_21", "rsi_14", "atr_14", "macd", "macd_signal", "macd_histogram", "volatility_20"}.issubset(result.columns)
    assert result["rsi_14"].iloc[-1] == pytest.approx(100.0)
