"""Read-only MT5 historical range support for reproducible research."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from mt5_scalping_agent.data.mt5_client import MT5DataError, MT5ReadOnlyClient


class MT5HistoricalRangeClient(MT5ReadOnlyClient):
    """Add explicit UTC-range candle retrieval without any execution operation."""

    def historical_ohlcv_range(self, symbol: str, timeframe: int, start: datetime, end: datetime) -> pd.DataFrame:
        self._require_nonempty_symbol(symbol)
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
        if start_utc >= end_utc:
            raise ValueError("start must be earlier than end")

        rates = self._mt5.copy_rates_range(symbol, timeframe, start_utc, end_utc)
        frame = _normalize_rates(rates, symbol, self._last_error())
        requested = frame.loc[(frame["time"] >= start_utc) & (frame["time"] < end_utc)].reset_index(drop=True)
        if requested.empty:
            raise MT5DataError(
                f"No historical rates returned inside requested range for {symbol}: {self._last_error()}"
            )
        return requested


def _normalize_rates(rates: Any, symbol: str, last_error: str) -> pd.DataFrame:
    if rates is None or len(rates) == 0:
        raise MT5DataError(f"No historical rates returned for {symbol}: {last_error}")

    frame = pd.DataFrame(rates)
    required_columns = {"time", "open", "high", "low", "close", "tick_volume"}
    missing = required_columns.difference(frame.columns)
    if missing:
        raise MT5DataError(f"Historical rates missing required fields: {sorted(missing)}")
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    return frame.sort_values("time").reset_index(drop=True)

