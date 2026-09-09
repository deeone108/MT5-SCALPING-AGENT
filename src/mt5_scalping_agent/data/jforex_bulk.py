"""Manifest-driven, local-only JForex monthly tick import pipeline."""

from __future__ import annotations

import calendar
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.histdata_tick_source import PAIRS
from mt5_scalping_agent.data.jforex_tick_source import JForexTickError, REQUIRED, import_jforex_ticks

MANIFEST_PATH = Path("reports/phase22_data_build/jforex_bulk_export_manifest.json")
INCOMING = Path("data/ticks/incoming/jforex")


def build_manifest(path: Path = MANIFEST_PATH, incoming: Path = INCOMING) -> dict[str, object]:
    units = []
    for pair in PAIRS:
        for year in range(2019, 2024):
            for month in range(1, 13):
                start = datetime(year, month, 1, tzinfo=UTC)
                end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
                filename = f"{pair}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}_JFOREX_TICKS.csv"
                units.append({
                    "pair": pair, "year": year, "month": month,
                    "start_utc": start.isoformat().replace("+00:00", "Z"),
                    "end_utc": end.isoformat().replace("+00:00", "Z"),
                    "expected_filename": filename, "landing_path": str(incoming / filename),
                    "status": "PENDING",
                })
    document = {"schema_version": 1, "partition": "calendar_month_utc", "expected_units": 240, "units": units}
    _write_json(path, document)
    return document


def process_bulk(manifest_path: Path = MANIFEST_PATH, data_root: Path = Path("data/ticks")) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for unit in manifest["units"]:
        if unit["status"] == "VALIDATED":
            if _verified_outputs(unit):
                continue
            unit["status"] = "FAILED"
            unit["error"] = "previously validated output hash no longer matches"
        source = Path(unit["landing_path"])
        if not source.is_file():
            continue
        try:
            metrics = _validate_unit(source, unit, data_root)
            unit.update(metrics)
            unit["status"] = "VALIDATED"
            unit.pop("error", None)
        except Exception as error:
            unit["status"] = "FAILED"
            unit["error"] = f"{type(error).__name__}: {error}"
        _write_json(manifest_path, manifest)
    manifest["roots"] = dataset_roots(manifest["units"])
    manifest["summary"] = {status: sum(unit["status"] == status for unit in manifest["units"])
                           for status in ("PENDING", "EXPORTED", "IMPORTED", "VALIDATED", "FAILED")}
    _write_json(manifest_path, manifest)
    return manifest


def _validate_unit(source: Path, unit: dict[str, object], data_root: Path) -> dict[str, object]:
    if source.name != unit["expected_filename"]:
        raise JForexTickError("filename does not match manifest unit")
    if not source.read_bytes().endswith((b"\n", b"\r\n")):
        raise JForexTickError("file appears truncated")
    raw = pd.read_csv(source)
    if tuple(raw.columns) != REQUIRED or raw.empty:
        raise JForexTickError("wrong or empty JForex CSV schema")
    numeric_cols = ["timestamp_utc_ms", "bid", "ask", "bid_volume", "ask_volume", "source_sequence"]
    try:
        numeric = raw[numeric_cols].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as error:
        raise JForexTickError("malformed numeric record") from error
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise JForexTickError("non-finite numeric record")
    if not raw["pair"].eq(unit["pair"]).all():
        raise JForexTickError("file pair does not match manifest unit")
    timestamps = pd.to_datetime(numeric["timestamp_utc_ms"], unit="ms", utc=True)
    start, end = pd.Timestamp(unit["start_utc"]), pd.Timestamp(unit["end_utc"])
    if ((timestamps < start) | (timestamps >= end)).any():
        raise JForexTickError("file timestamp is outside manifest month")
    if not ((numeric.bid > 0) & (numeric.ask > 0) & (numeric.ask >= numeric.bid)).all():
        raise JForexTickError("non-positive or crossed quote")
    imported = import_jforex_ticks(source, data_root)
    frame = pd.read_parquet(imported["normalized_path"])
    deltas = np.diff(frame["timestamp_utc_ns"].to_numpy(np.int64)) / 1_000_000
    same_time = frame.duplicated("timestamp_utc_ns", keep=False)
    same_quote = frame.duplicated(["timestamp_utc_ns", "bid", "ask"], keep=False)
    exact = frame.duplicated(["timestamp_utc_ns", "bid", "ask", "bid_volume", "ask_volume"], keep=False)
    return {
        **imported, "status": "VALIDATED", "first_timestamp_utc": timestamps.min().isoformat(),
        "last_timestamp_utc": timestamps.max().isoformat(), "raw_bytes": source.stat().st_size,
        "normalized_bytes": Path(imported["normalized_path"]).stat().st_size,
        "exact_duplicate_rows": int(exact.sum()),
        "same_timestamp_same_quote_rows": int((same_time & same_quote & ~exact).sum()),
        "same_timestamp_different_quote_rows": int((same_time & ~same_quote).sum()),
        "long_gaps_over_60s": int((deltas > 60_000).sum()),
    }


def dataset_roots(units: list[dict[str, object]]) -> dict[str, object]:
    valid = [unit for unit in units if unit["status"] == "VALIDATED"]
    def root(rows: list[dict[str, object]]) -> str:
        evidence = "".join(
            f"{row['pair']}|{row['year']}|{row['month']:02d}|{row['raw_sha256']}|{row['normalized_sha256']}|{row['ticks']}\n"
            for row in sorted(rows, key=lambda item: (item["pair"], item["year"], item["month"]))
        )
        return hashlib.sha256(evidence.encode()).hexdigest()
    pair_year = {f"{pair}_{year}": root([u for u in valid if u["pair"] == pair and u["year"] == year])
                 for pair in PAIRS for year in range(2019, 2024)
                 if any(u["pair"] == pair and u["year"] == year for u in valid)}
    pair = {name: root([u for u in valid if u["pair"] == name]) for name in PAIRS
            if any(u["pair"] == name for u in valid)}
    return {"pair_year": pair_year, "pair": pair, "dataset": root(valid) if len(valid) == 240 else None}


def _verified_outputs(unit: dict[str, object]) -> bool:
    try:
        return (hashlib.sha256(Path(unit["raw_path"]).read_bytes()).hexdigest() == unit["raw_sha256"]
                and hashlib.sha256(Path(unit["normalized_path"]).read_bytes()).hexdigest() == unit["normalized_sha256"])
    except (KeyError, OSError):
        return False


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
