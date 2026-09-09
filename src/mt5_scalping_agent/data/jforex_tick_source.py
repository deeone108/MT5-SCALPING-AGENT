"""Offline importer for the frozen JForex4 historical-tick export schema."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.histdata_tick_source import PAIRS, PIP_SIZES

REQUIRED = ("timestamp_utc_ms", "pair", "bid", "ask", "bid_volume", "ask_volume", "source_sequence")


class JForexTickError(RuntimeError):
    """Raised when a JForex export cannot be preserved and normalized safely."""


def import_jforex_ticks(source: Path, root: Path = Path("data/ticks")) -> dict[str, object]:
    payload = source.read_bytes()
    raw_hash = hashlib.sha256(payload).hexdigest()
    try:
        frame = pd.read_csv(source)
    except (OSError, pd.errors.ParserError) as error:
        raise JForexTickError("could not parse JForex CSV") from error
    if tuple(frame.columns) != REQUIRED or frame.empty:
        raise JForexTickError(f"expected exact columns: {', '.join(REQUIRED)}")
    if frame["pair"].nunique() != 1 or (pair := str(frame["pair"].iloc[0])) not in PAIRS:
        raise JForexTickError("export must contain exactly one authorized pair")
    numeric = frame[["timestamp_utc_ms", "bid", "ask", "bid_volume", "ask_volume", "source_sequence"]]
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise JForexTickError("export contains non-finite values")
    if not ((frame["bid"] > 0) & (frame["ask"] >= frame["bid"])).all():
        raise JForexTickError("export contains invalid or crossed quotes")
    timestamp = pd.to_datetime(frame["timestamp_utc_ms"], unit="ms", utc=True)
    if timestamp.min() < pd.Timestamp("2019-01-01T00:00:00Z") or timestamp.max() >= pd.Timestamp("2024-01-01T00:00:00Z"):
        raise JForexTickError("export contains timestamps outside Phase 22 development scope")
    normalized = pd.DataFrame({
        "timestamp_utc_ns": timestamp.astype("int64"), "pair": pair,
        "bid": frame["bid"].astype(float), "ask": frame["ask"].astype(float),
        "source_volume": pd.NA, "source_sequence": frame["source_sequence"].astype("int64"),
        "source_provider": "jforex", "source_file": source.name,
        "raw_row_number": pd.RangeIndex(len(frame), dtype="int64"),
        "bid_volume": frame["bid_volume"].astype(float), "ask_volume": frame["ask_volume"].astype(float),
    }).sort_values(["timestamp_utc_ns", "source_sequence"], kind="stable").reset_index(drop=True)
    normalized["mid_price"] = (normalized["bid"] + normalized["ask"]) / 2
    normalized["spread_price"] = normalized["ask"] - normalized["bid"]
    normalized["spread_pips"] = normalized["spread_price"] / PIP_SIZES[pair]
    stamp = timestamp.min()
    unit = Path(pair) / str(stamp.year) / f"{stamp.month:02d}"
    raw_path = root / "raw" / "jforex" / unit / source.name
    parquet_path = root / "normalized" / "jforex" / unit / "ticks.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and hashlib.sha256(raw_path.read_bytes()).hexdigest() != raw_hash:
        raise JForexTickError("immutable raw destination differs")
    if not raw_path.exists(): shutil.copyfile(source, raw_path)
    normalized.to_parquet(parquet_path, compression="zstd", index=False)
    result = {"provider": "jforex", "pair": pair, "ticks": len(normalized), "raw_path": str(raw_path),
              "raw_sha256": raw_hash, "normalized_path": str(parquet_path),
              "normalized_sha256": hashlib.sha256(parquet_path.read_bytes()).hexdigest(),
              "first_timestamp_utc": timestamp.min().isoformat(), "last_timestamp_utc": timestamp.max().isoformat()}
    manifest = root / "manifests" / "jforex_import.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
