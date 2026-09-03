"""Read-only, chunked M1 history adapter for the public Dukascopy data feed."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import dukascopy_python as dukascopy
import pandas as pd

from mt5_scalping_agent.data.validation import validate_ohlcv


class DukascopyDataError(RuntimeError):
    """Raised when public historical data cannot safely be normalized or used."""


INSTRUMENTS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCAD": "USD/CAD",
}


class DukascopyM1Client:
    """Fetch public bid-side M1 bars with explicit date bounds and no trading access."""

    def __init__(self, fetcher: Callable[..., pd.DataFrame] = dukascopy.fetch) -> None:
        self._fetcher = fetcher

    def historical_ohlcv(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Return validated M1 OHLCV bars strictly inside the requested UTC interval."""
        start_utc, end_utc = _validate_range(start, end)
        instrument = INSTRUMENTS.get(symbol.upper())
        if instrument is None:
            raise ValueError(f"Unsupported Dukascopy symbol: {symbol}")

        raw = self._fetcher(
            instrument,
            dukascopy.INTERVAL_MIN_1,
            dukascopy.OFFER_SIDE_BID,
            start_utc,
            end_utc,
        )
        if raw.empty:
            raise DukascopyDataError(f"No Dukascopy M1 bars returned for {symbol} in the requested range")
        if raw.index.name != "timestamp":
            raise DukascopyDataError("Unexpected Dukascopy response: timestamp index is missing")

        frame = raw.reset_index().rename(columns={"timestamp": "time", "volume": "tick_volume"})
        required = {"time", "open", "high", "low", "close", "tick_volume"}
        if missing := required.difference(frame.columns):
            raise DukascopyDataError(f"Dukascopy response is missing columns: {sorted(missing)}")
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.loc[(frame["time"] >= start_utc) & (frame["time"] < end_utc), list(required)].sort_values("time")
        if frame.empty:
            raise DukascopyDataError(f"No Dukascopy M1 bars remained inside the requested range for {symbol}")
        return validate_ohlcv(frame.reset_index(drop=True))

    def iter_historical_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        chunk_days: int = 14,
    ) -> Iterator[pd.DataFrame]:
        """Yield bounded date chunks suitable for resumable long-history imports."""
        start_utc, end_utc = _validate_range(start, end)
        if chunk_days <= 0 or chunk_days > 20:
            raise ValueError("chunk_days must be between 1 and 20")

        cursor = start_utc
        while cursor < end_utc:
            chunk_end = min(cursor + timedelta(days=chunk_days), end_utc)
            try:
                yield self.historical_ohlcv(symbol, cursor, chunk_end)
            except DukascopyDataError as error:
                if "No Dukascopy M1 bars returned" not in str(error):
                    raise
            cursor = chunk_end


def _validate_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    if start_utc >= end_utc:
        raise ValueError("start must be earlier than end")
    return start_utc, end_utc
