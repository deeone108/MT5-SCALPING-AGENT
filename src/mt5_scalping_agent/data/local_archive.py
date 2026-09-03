"""Validated access to locally stored, source-segmented research archives."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from mt5_scalping_agent.data.validation import validate_ohlcv


class LocalArchiveError(RuntimeError):
    """Raised when a requested local research window is unavailable or unsafe."""


PROVIDER_BOUNDARY = datetime(2019, 1, 1, tzinfo=UTC)
_SOURCE_DIRECTORIES = {"histdata": "histdata", "dukascopy": "dukascopy_annual"}


class LocalResearchArchive:
    """Load annual M1 archives without hiding the 2019 provider boundary."""

    def __init__(self, root: Path = Path("data")) -> None:
        self._root = root

    def source_for_range(self, start: datetime, end: datetime) -> str:
        """Return the sole provider for a range or reject a cross-provider request."""
        normalized_start, normalized_end = _validate_range(start, end)
        if normalized_start < PROVIDER_BOUNDARY < normalized_end:
            raise LocalArchiveError(
                "requested range crosses the 2019-01-01 provider boundary; "
                "run HistData and Dukascopy windows separately"
            )
        return "histdata" if normalized_end <= PROVIDER_BOUNDARY else "dukascopy"

    def load_m1(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Load and validate a single-provider, half-open UTC M1 time range."""
        normalized_start, normalized_end = _validate_range(start, end)
        source = self.source_for_range(normalized_start, normalized_end)
        normalized_symbol = symbol.upper()
        last_included_year = (pd.Timestamp(normalized_end) - pd.Timedelta(1, unit="us")).year
        files = self._annual_files(normalized_symbol, source, normalized_start.year, last_included_year)
        combined = pd.concat([_read_annual_file(path) for path in files], ignore_index=True)
        selected = combined.loc[
            (combined["time"] >= pd.Timestamp(normalized_start))
            & (combined["time"] < pd.Timestamp(normalized_end))
        ].reset_index(drop=True)
        if selected.empty:
            raise LocalArchiveError(
                f"local {source} archive contains no {normalized_symbol} M1 bars in "
                f"[{normalized_start.isoformat()}, {normalized_end.isoformat()})"
            )
        try:
            return validate_ohlcv(selected)
        except ValueError as error:
            raise LocalArchiveError(f"local {source} archive failed OHLCV validation") from error

    def _annual_files(self, symbol: str, source: str, start_year: int, end_year: int) -> list[Path]:
        directory = self._root / _SOURCE_DIRECTORIES[source]
        files = [directory / f"{symbol}_m1_{year}.csv.gz" for year in range(start_year, end_year + 1)]
        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise LocalArchiveError(f"local {source} archive is missing annual files: {', '.join(missing)}")
        return files


def resample_m1_to_m5(
    m1: pd.DataFrame,
    *,
    incomplete: Literal["drop", "raise", "keep"] = "drop",
) -> pd.DataFrame:
    """Build causal M5 candles with explicit constituent-completeness handling.

    The default excludes incomplete buckets and records their count in
    ``DataFrame.attrs``. ``keep`` retains them with ``is_complete=False``;
    ``raise`` rejects the input. Empty market-closure buckets are not candles and
    are not reported as incomplete constituent buckets.
    """
    if incomplete not in {"drop", "raise", "keep"}:
        raise ValueError("incomplete must be one of: drop, raise, keep")
    validated = validate_ohlcv(m1)
    if (validated["time"].dt.floor("min") != validated["time"]).any():
        raise LocalArchiveError("M1 timestamps must be aligned to whole minutes before M5 resampling")
    m5 = (
        validated.set_index("time")
        .resample("5min", label="left", closed="left")
        .agg(
            open=("open", "first"), high=("high", "max"), low=("low", "min"),
            close=("close", "last"), tick_volume=("tick_volume", "sum"),
            m1_count=("close", "count"),
        )
        .dropna()
        .reset_index()
    )
    m5["m1_count"] = m5["m1_count"].astype(int)
    m5["is_complete"] = m5["m1_count"] == 5
    incomplete_rows = m5.loc[~m5["is_complete"], ["time", "m1_count"]]
    if incomplete == "raise" and not incomplete_rows.empty:
        first = incomplete_rows.iloc[0]
        raise LocalArchiveError(
            f"M5 bucket {first['time'].isoformat()} has {int(first['m1_count'])}/5 M1 constituents"
        )
    if incomplete == "drop":
        m5 = m5.loc[m5["is_complete"]].reset_index(drop=True)
    if m5.empty:
        raise LocalArchiveError("M1 data contains no complete M5 buckets")
    result = validate_ohlcv(m5)
    result.attrs["m5_completeness_policy"] = incomplete
    result.attrs["incomplete_m5_bars"] = len(incomplete_rows)
    result.attrs["incomplete_m5_examples"] = [
        {"time": row.time.isoformat(), "m1_count": int(row.m1_count)}
        for row in incomplete_rows.head(20).itertuples(index=False)
    ]
    return result


def _validate_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("archive timestamps must be timezone-aware")
    normalized_start, normalized_end = start.astimezone(UTC), end.astimezone(UTC)
    if normalized_start >= normalized_end:
        raise ValueError("start must be before end")
    return normalized_start, normalized_end


def _read_annual_file(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, compression="gzip")
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="raise")
        return frame
    except (OSError, KeyError, ValueError, pd.errors.ParserError) as error:
        raise LocalArchiveError(f"could not read local annual archive: {path}") from error
