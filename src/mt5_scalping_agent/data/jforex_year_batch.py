"""Pure UTC partition and routing rules used by YEAR_BATCH evidence and tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def month_bounds(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(datetime(year, month, 1, tzinfo=UTC))
    end = pd.Timestamp(datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC))
    return start, end


def validate_batch_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("batch output directory must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or not os.access(resolved, os.W_OK):
        raise ValueError("batch output directory must exist and be writable")
    return resolved


def routed_months(tick_months: list[int], protected: set[int]) -> list[int]:
    """Model independent month initialization; protection never terminates routing."""
    if not protected <= set(range(1, 13)):
        raise ValueError("protected month outside 1..12")
    return [month for month in tick_months if month not in protected]


def partition_year_ticks(frame: pd.DataFrame, year: int) -> dict[int, pd.DataFrame]:
    """Partition without duplicates/omissions; preserve source order per month."""
    timestamps = pd.to_datetime(frame["timestamp_utc_ms"], unit="ms", utc=True)
    year_start, _ = month_bounds(year, 1)
    _, year_end = month_bounds(year, 12)
    if ((timestamps < year_start) | (timestamps >= year_end)).any():
        raise ValueError("tick falls outside YEAR_BATCH bounds")
    result = {}
    for month in range(1, 13):
        start, end = month_bounds(year, month)
        selected = frame.loc[(timestamps >= start) & (timestamps < end)].copy()
        selected["source_sequence"] = range(len(selected))
        result[month] = selected.reset_index(drop=True)
    return result