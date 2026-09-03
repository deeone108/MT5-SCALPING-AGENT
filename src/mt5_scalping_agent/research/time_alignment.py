"""Timestamp-alignment primitives for research outcomes."""
from __future__ import annotations
from collections.abc import Iterable
import numpy as np
import pandas as pd

def validated_time_index(values: Iterable[object], *, name: str = "time") -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(values, errors="raise"))
    if index.tz is None:
        raise ValueError(f"{name} must be timezone-aware")
    index = index.tz_convert("UTC")
    if index.hasnans:
        raise ValueError(f"{name} contains missing timestamps")
    if index.has_duplicates:
        raise ValueError(f"{name} contains duplicate timestamps")
    if not index.is_monotonic_increasing:
        raise ValueError(f"{name} must be sorted ascending")
    return index

def exact_positions(index: pd.DatetimeIndex, origins: Iterable[object], offsets_minutes: Iterable[int]) -> tuple[np.ndarray, np.ndarray]:
    """Locate exact elapsed-minute endpoints; absent timestamps map to -1."""
    source = validated_time_index(index)
    origin_index = pd.DatetimeIndex(pd.to_datetime(origins, errors="raise"))
    if origin_index.tz is None:
        raise ValueError("event_time must be timezone-aware")
    origin_index = origin_index.tz_convert("UTC")
    origin_positions = source.get_indexer(origin_index)
    offsets = np.asarray(tuple(offsets_minutes), dtype=int)
    if (offsets < 0).any():
        raise ValueError("offsets_minutes must be nonnegative")
    positions = np.column_stack([
        source.get_indexer(origin_index + pd.Timedelta(int(offset), unit="min"))
        for offset in offsets
    ])
    return origin_positions, positions
