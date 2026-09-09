"""Frozen Phase 22 JForex pilot validation and deterministic replay evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.jforex_tick_source import JForexTickError, REQUIRED, import_jforex_ticks

PILOT_START = pd.Timestamp("2019-01-07T00:00:00Z")
PILOT_END = pd.Timestamp("2019-01-14T00:00:00Z")
PILOT_FILENAME = "EURUSD_20190107T000000Z_20190114T000000Z_JFOREX_TICKS.csv"
PILOT_LANDING = Path("data/ticks/incoming/jforex")


def validate_jforex_pilot(source: Path, root: Path = Path("data/ticks")) -> dict[str, object]:
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise JForexTickError(f"pilot file unavailable: {source}") from error
    if not payload or not payload.endswith((b"\n", b"\r\n")):
        raise JForexTickError("pilot is empty or appears truncated (missing terminal newline)")
    try:
        raw = pd.read_csv(source, dtype={"pair": "string"})
    except (OSError, pd.errors.ParserError) as error:
        raise JForexTickError("malformed pilot CSV") from error
    if tuple(raw.columns) != REQUIRED or raw.empty:
        raise JForexTickError(f"expected exact columns: {', '.join(REQUIRED)}")
    if raw.astype("string").eq("timestamp_utc_ms").any(axis=None):
        raise JForexTickError("duplicate CSV header found in data rows")
    numeric_columns = ["timestamp_utc_ms", "bid", "ask", "bid_volume", "ask_volume", "source_sequence"]
    try:
        numeric = raw[numeric_columns].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as error:
        raise JForexTickError("pilot contains malformed numeric values") from error
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise JForexTickError("pilot contains non-finite numeric values")
    if not raw["pair"].eq("EURUSD").all():
        raise JForexTickError("frozen pilot must contain EURUSD only")
    timestamps = pd.to_datetime(numeric["timestamp_utc_ms"], unit="ms", utc=True, errors="raise")
    if ((timestamps < PILOT_START) | (timestamps >= PILOT_END)).any():
        raise JForexTickError("pilot timestamps must remain inside the frozen half-open interval")
    if not ((numeric["bid"] > 0) & (numeric["ask"] > 0) & (numeric["ask"] >= numeric["bid"])).all():
        raise JForexTickError("pilot contains non-positive or crossed quotes")

    imported = import_jforex_ticks(source, root)
    frame = pd.read_parquet(imported["normalized_path"])
    replay_one = _replay_hash(frame)
    replay_two = _replay_hash(frame)
    if replay_one != replay_two:
        raise JForexTickError("pilot replay is not deterministic")

    time_ms = frame["timestamp_utc_ns"].astype("int64") / 1_000_000
    deltas = pd.Series(np.diff(time_ms), dtype=float)
    same_time = frame.duplicated("timestamp_utc_ns", keep=False)
    same_quote = frame.duplicated(["timestamp_utc_ns", "bid", "ask"], keep=False)
    exact = frame.duplicated(
        ["timestamp_utc_ns", "bid", "ask", "bid_volume", "ask_volume"], keep=False
    )
    spread = frame["spread_pips"].astype(float)
    parquet_bytes = Path(imported["normalized_path"]).stat().st_size
    quality = {
        **imported,
        "timestamp_precision": "milliseconds",
        "crossed_quotes": int((frame["ask"] < frame["bid"]).sum()),
        "non_positive_quotes": int(((frame["bid"] <= 0) | (frame["ask"] <= 0)).sum()),
        "bid_volume_available": bool(frame["bid_volume"].notna().all()),
        "ask_volume_available": bool(frame["ask_volume"].notna().all()),
        "spread_pips": _percentiles(spread),
        "inter_tick_ms": _percentiles(deltas) if not deltas.empty else {},
        "exact_duplicate_rows": int(exact.sum()),
        "same_timestamp_same_quote_rows": int((same_time & same_quote & ~exact).sum()),
        "same_timestamp_different_quote_rows": int((same_time & ~same_quote).sum()),
        "long_gaps_over_60s": int((deltas > 60_000).sum()),
        "raw_bytes": len(payload), "parquet_bytes": parquet_bytes,
        "compression_ratio": len(payload) / parquet_bytes,
        "raw_bytes_per_tick": len(payload) / len(frame),
        "parquet_bytes_per_tick": parquet_bytes / len(frame),
        "replay_sha256": replay_one, "replay_repeated_identically": True,
    }
    root_hash_input = f"{quality['raw_sha256']}\n{quality['normalized_sha256']}\n{replay_one}\n".encode()
    quality["pilot_root_sha256"] = hashlib.sha256(root_hash_input).hexdigest()
    report = root / "manifests" / "jforex_pilot_quality.json"
    report.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return quality


def _percentiles(values: pd.Series) -> dict[str, float]:
    return {name: float(values.quantile(q)) for name, q in (("p50", .5), ("p90", .9), ("p95", .95), ("p99", .99), ("max", 1.0))}


def _replay_hash(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values(["timestamp_utc_ns", "source_sequence"], kind="stable")
    if not ordered["timestamp_utc_ns"].is_monotonic_increasing:
        raise JForexTickError("replay is not chronological")
    columns = ["timestamp_utc_ns", "bid", "ask", "bid_volume", "ask_volume", "source_sequence"]
    return hashlib.sha256(ordered[columns].to_csv(index=False, lineterminator="\n").encode()).hexdigest()
