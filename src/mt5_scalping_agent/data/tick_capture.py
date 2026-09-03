"""Read-only broker tick and spread capture for research calibration."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mt5_scalping_agent.data.mt5_client import MT5DataError, MT5ReadOnlyClient


class TickCaptureError(MT5DataError):
    """Raised when a terminal tick cannot be normalized for research."""


class TickSpreadRecorder:
    """Capture validated bid/ask observations without execution operations."""

    fieldnames = ("observed_at", "tick_time", "symbol", "bid", "ask", "spread_points")

    def __init__(self, client: MT5ReadOnlyClient) -> None:
        self._client = client

    def capture(self, symbol: str, observed_at: datetime | None = None) -> dict[str, object]:
        """Read one latest tick and return a normalized research record."""
        self._client.select_symbol(symbol)
        tick = self._client.tick(symbol)
        metadata = self._client.symbol_information(symbol)
        point = _positive_float(metadata.get("point"), "symbol point")
        bid = _positive_float(tick.get("bid"), "bid")
        ask = _positive_float(tick.get("ask"), "ask")
        if ask < bid:
            raise TickCaptureError("tick ask must not be below bid")
        now = observed_at or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return {
            "observed_at": now.astimezone(UTC).isoformat(),
            "tick_time": _tick_timestamp(tick).isoformat(),
            "symbol": symbol.upper(),
            "bid": bid,
            "ask": ask,
            "spread_points": round((ask - bid) / point, 10),
        }

    def append_csv(self, path: Path, record: dict[str, object]) -> None:
        """Append one normalized record, creating the CSV header only once."""
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(record)


def _tick_timestamp(tick: dict[str, Any]) -> datetime:
    if tick.get("time_msc") is not None:
        return datetime.fromtimestamp(int(tick["time_msc"]) / 1_000, tz=UTC)
    if tick.get("time") is not None:
        return datetime.fromtimestamp(int(tick["time"]), tz=UTC)
    raise TickCaptureError("tick has no time or time_msc field")


def _positive_float(value: Any, description: str) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise TickCaptureError(f"{description} is missing or invalid") from error
    if converted <= 0:
        raise TickCaptureError(f"{description} must be greater than zero")
    return converted
