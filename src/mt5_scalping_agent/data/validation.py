"""Validation for normalized OHLCV data before analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd


class MarketDataValidationError(ValueError):
    """Raised when OHLCV data cannot safely be used for analysis."""


REQUIRED_OHLCV_COLUMNS = frozenset({"time", "open", "high", "low", "close", "tick_volume"})
PRICE_COLUMNS = ("open", "high", "low", "close")


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a validated copy of chronological, UTC OHLCV data."""
    if frame.empty:
        raise MarketDataValidationError("OHLCV data is empty")

    missing = REQUIRED_OHLCV_COLUMNS.difference(frame.columns)
    if missing:
        raise MarketDataValidationError(f"OHLCV data is missing columns: {sorted(missing)}")

    validated = frame.copy()
    if not isinstance(validated["time"].dtype, pd.DatetimeTZDtype):
        raise MarketDataValidationError("OHLCV timestamps must be timezone-aware")
    if str(validated["time"].dt.tz) != "UTC":
        validated["time"] = validated["time"].dt.tz_convert("UTC")

    if validated["time"].isna().any() or validated[list(PRICE_COLUMNS)].isna().any().any():
        raise MarketDataValidationError("OHLCV data contains missing timestamps or prices")
    if validated["time"].duplicated().any():
        raise MarketDataValidationError("OHLCV data contains duplicate timestamps")
    if not validated["time"].is_monotonic_increasing:
        raise MarketDataValidationError("OHLCV timestamps must be sorted ascending")
    if (validated["tick_volume"] < 0).any():
        raise MarketDataValidationError("OHLCV tick volume cannot be negative")
    if (validated["high"] < validated[["open", "close", "low"]].max(axis=1)).any():
        raise MarketDataValidationError("OHLCV high is below another bar price")
    if (validated["low"] > validated[["open", "close", "high"]].min(axis=1)).any():
        raise MarketDataValidationError("OHLCV low is above another bar price")

    return validated


def assert_data_is_fresh(
    frame: pd.DataFrame,
    maximum_age: timedelta,
    now: datetime | None = None,
) -> None:
    """Reject data whose newest candle is older than the caller's limit."""
    if maximum_age <= timedelta(0):
        raise ValueError("maximum_age must be positive")

    validated = validate_ohlcv(frame)
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    newest = validated["time"].iloc[-1].to_pydatetime()
    if current_time.astimezone(UTC) - newest > maximum_age:
        raise MarketDataValidationError(
            f"OHLCV data is stale: newest candle is {newest.isoformat()}, "
            f"maximum permitted age is {maximum_age}"
        )
