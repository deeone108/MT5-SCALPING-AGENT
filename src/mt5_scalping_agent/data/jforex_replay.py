"""Provider-neutral deterministic replay for normalized JForex partitions."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path

import pandas as pd

from mt5_scalping_agent.data.jforex_tick_source import JForexTickError

REPLAY_COLUMNS = ("timestamp_utc_ns", "pair", "bid", "ask", "bid_volume", "ask_volume", "source_sequence")


def replay_partitions(paths: Sequence[Path], start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> Iterator[dict[str, object]]:
    """Yield only real stored ticks in stable timestamp/source order and half-open bounds."""
    if start_utc.tzinfo is None or end_utc.tzinfo is None or start_utc >= end_utc:
        raise ValueError("replay requires ordered timezone-aware bounds")
    frames = [pd.read_parquet(path, columns=list(REPLAY_COLUMNS)) for path in paths]
    if not frames:
        return
    frame = pd.concat(frames, ignore_index=True).sort_values(
        ["timestamp_utc_ns", "source_sequence"], kind="stable"
    )
    start_ns, end_ns = start_utc.value, end_utc.value
    selected = frame.loc[(frame.timestamp_utc_ns >= start_ns) & (frame.timestamp_utc_ns < end_ns)]
    if not selected.timestamp_utc_ns.is_monotonic_increasing:
        raise JForexTickError("replay ordering failure")
    for row in selected.itertuples(index=False):
        yield {column: getattr(row, column) for column in REPLAY_COLUMNS}


def replay_sha256(rows: Sequence[dict[str, object]]) -> str:
    payload = pd.DataFrame(rows, columns=REPLAY_COLUMNS).to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(payload.encode()).hexdigest()
