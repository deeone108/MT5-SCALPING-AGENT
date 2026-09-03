from datetime import timedelta

import pandas as pd
import pytest

from mt5_scalping_agent.data.validation import MarketDataValidationError, assert_data_is_fresh, validate_ohlcv


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4],
            "low": [0.9, 1.0, 1.1],
            "close": [1.1, 1.2, 1.3],
            "tick_volume": [10, 11, 12],
        }
    )


def test_validates_well_formed_ohlcv() -> None:
    assert validate_ohlcv(valid_frame()).equals(valid_frame())


@pytest.mark.parametrize("column", ["time", "open", "high", "low", "close", "tick_volume"])
def test_rejects_missing_required_column(column: str) -> None:
    with pytest.raises(MarketDataValidationError, match="missing columns"):
        validate_ohlcv(valid_frame().drop(columns=column))


def test_rejects_duplicate_or_unsorted_timestamps() -> None:
    duplicate = valid_frame()
    duplicate.loc[2, "time"] = duplicate.loc[1, "time"]
    with pytest.raises(MarketDataValidationError, match="duplicate"):
        validate_ohlcv(duplicate)

    unsorted = valid_frame().iloc[::-1].reset_index(drop=True)
    with pytest.raises(MarketDataValidationError, match="sorted"):
        validate_ohlcv(unsorted)


def test_detects_stale_data_with_explicit_limit() -> None:
    frame = valid_frame()
    with pytest.raises(MarketDataValidationError, match="stale"):
        assert_data_is_fresh(
            frame,
            maximum_age=timedelta(minutes=1),
            now=frame["time"].iloc[-1].to_pydatetime() + timedelta(minutes=2),
        )

