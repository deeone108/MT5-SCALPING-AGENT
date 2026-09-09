"""Resumable, read-only MT5 historical tick acquisition for Phase 22."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
YEARS = range(2019, 2024)
PROVIDER = "ROBOFOREX_MT5"
RAW_FIELDS = ("time", "bid", "ask", "last", "volume", "time_msc", "flags", "volume_real")
NORMALIZED_FIELDS = (
    "timestamp_utc_ns", "pair", "bid", "ask", "last", "source_volume",
    "source_volume_real", "tick_flags", "source_provider", "source_sequence",
    "mid_price", "spread_price", "spread_pips",
)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def build_manifest(path: Path, data_root: Path) -> dict[str, Any]:
    units = []
    for pair in PAIRS:
        for year in YEARS:
            for month in range(1, 13):
                start, end = month_bounds(year, month)
                stem = f"{pair}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}_MT5_TICKS"
                units.append(
                    {
                        "pair": pair,
                        "year": year,
                        "month": month,
                        "start_utc": start.isoformat(),
                        "end_utc": end.isoformat(),
                        "status": "PENDING",
                        "raw_path": str(data_root / "raw" / PROVIDER / pair / str(year) / f"{stem}.npz"),
                        "normalized_path": str(data_root / "normalized" / PROVIDER / pair / str(year) / f"{stem}.parquet"),
                        "metadata_path": str(data_root / "raw" / PROVIDER / pair / str(year) / f"{stem}.metadata.json"),
                    }
                )
    manifest = {
        "schema_version": 1,
        "source_provider": PROVIDER,
        "acquisition_api": "MetaTrader5.copy_ticks_range/COPY_TICKS_ALL",
        "development_interval": "[2019-01-01T00:00:00Z, 2024-01-01T00:00:00Z)",
        "units": units,
    }
    _atomic_json(path, manifest)
    return manifest


def normalize_ticks(raw: np.ndarray, pair: str, start: datetime, end: datetime) -> pd.DataFrame:
    missing = set(RAW_FIELDS).difference(raw.dtype.names or ())
    if missing:
        raise ValueError(f"MT5 tick schema missing fields: {sorted(missing)}")
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    selected = raw[(raw["time_msc"] >= start_ms) & (raw["time_msc"] < end_ms)]
    if len(selected) == 0:
        raise ValueError("MT5 returned no ticks in the requested half-open month")
    bid = selected["bid"].astype("float64")
    ask = selected["ask"].astype("float64")
    if np.any(bid <= 0) or np.any(ask <= 0) or np.any(ask < bid):
        raise ValueError("invalid bid/ask values in MT5 response")
    times = selected["time_msc"].astype("int64")
    if np.any(np.diff(times) < 0):
        raise ValueError("MT5 ticks are not monotonic by time_msc")
    pip_size = 0.01 if pair.endswith("JPY") else 0.0001
    frame = pd.DataFrame(
        {
            "timestamp_utc_ns": times * 1_000_000,
            "pair": pair,
            "bid": bid,
            "ask": ask,
            "last": selected["last"].astype("float64"),
            "source_volume": selected["volume"].astype("int64"),
            "source_volume_real": selected["volume_real"].astype("float64"),
            "tick_flags": selected["flags"].astype("uint32"),
            "source_provider": PROVIDER,
            "source_sequence": np.arange(len(selected), dtype="int64"),
        }
    )
    frame["mid_price"] = (frame["bid"] + frame["ask"]) / 2
    frame["spread_price"] = frame["ask"] - frame["bid"]
    frame["spread_pips"] = frame["spread_price"] / pip_size
    return frame.loc[:, NORMALIZED_FIELDS]


def quality_summary(frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = frame["timestamp_utc_ns"].to_numpy(dtype="int64")
    duplicate_timestamps = int(pd.Series(timestamps).duplicated(keep=False).sum())
    source_values = frame.drop(columns=["source_sequence"])
    duplicate_rows = int(source_values.duplicated(keep=False).sum())
    gaps_ms = np.diff(timestamps) / 1_000_000
    return {
        "tick_count": len(frame),
        "first_tick_utc": pd.Timestamp(timestamps[0], unit="ns", tz="UTC").isoformat(),
        "last_tick_utc": pd.Timestamp(timestamps[-1], unit="ns", tz="UTC").isoformat(),
        "duplicate_timestamp_rows": duplicate_timestamps,
        "exact_duplicate_rows": duplicate_rows,
        "same_timestamp_distinct_rows": max(duplicate_timestamps - duplicate_rows, 0),
        "gaps_over_1_second": int((gaps_ms > 1_000).sum()),
        "gaps_over_60_seconds": int((gaps_ms > 60_000).sum()),
        "maximum_gap_ms": float(gaps_ms.max()) if len(gaps_ms) else 0.0,
        "timestamp_precision": "milliseconds (time_msc), stored as UTC nanoseconds",
        "monotonic": bool(np.all(np.diff(timestamps) >= 0)),
        "invalid_bid_ask_rows": int(
            ((frame["bid"] <= 0) | (frame["ask"] <= 0) | (frame["ask"] < frame["bid"])).sum()
        ),
    }


def persist_unit(
    raw: np.ndarray,
    unit: dict[str, Any],
    *,
    broker: str,
    server: str,
    account_mode: str,
    package_version: str,
    terminal_build: str | int | None,
) -> dict[str, Any]:
    raw_path = Path(unit["raw_path"])
    normalized_path = Path(unit["normalized_path"])
    metadata_path = Path(unit["metadata_path"])
    for path in (raw_path, normalized_path, metadata_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(unit["start_utc"])
    end = datetime.fromisoformat(unit["end_utc"])
    frame = normalize_ticks(raw, unit["pair"], start, end)

    raw_part = raw_path.with_suffix(raw_path.suffix + ".part")
    normalized_part = normalized_path.with_suffix(normalized_path.suffix + ".part")
    metadata_part = metadata_path.with_suffix(metadata_path.suffix + ".part")
    committed: list[Path] = []
    try:
        with raw_part.open("xb") as handle:
            np.savez_compressed(handle, ticks=raw)
        frame.to_parquet(normalized_part, index=False)
        raw_hash = _sha256(raw_part)
        normalized_hash = _sha256(normalized_part)
        metadata = {
            "source_provider": PROVIDER,
            "broker": broker,
            "server": server,
            "account_mode": account_mode,
            "symbol": unit["pair"],
            "request_start_utc": unit["start_utc"],
            "request_end_utc": unit["end_utc"],
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "mt5_package_version": package_version,
            "terminal_build": terminal_build,
            "raw_fields": list(raw.dtype.names or ()),
            "raw_response_rows": len(raw),
            "raw_sha256": raw_hash,
            "normalized_sha256": normalized_hash,
            "quality": quality_summary(frame),
        }
        metadata_part.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        for temporary, final in (
            (raw_part, raw_path),
            (normalized_part, normalized_path),
            (metadata_part, metadata_path),
        ):
            os.replace(temporary, final)
            committed.append(final)
        return metadata
    except Exception:
        for path in (raw_part, normalized_part, metadata_part, *committed):
            path.unlink(missing_ok=True)
        raise


def acquire_next(client: Any, manifest_path: Path, mt5_module: Any) -> dict[str, Any] | None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unit = next((item for item in manifest["units"] if item["status"] != "VALIDATED"), None)
    if unit is None:
        return None
    client.select_symbol(unit["pair"])
    start = datetime.fromisoformat(unit["start_utc"])
    end = datetime.fromisoformat(unit["end_utc"])
    raw = client.historical_ticks_raw(unit["pair"], start, end)
    account = client.account_information()
    terminal = mt5_module.terminal_info()
    try:
        metadata = persist_unit(
            raw,
            unit,
            broker=str(account.get("company") or "unknown"),
            server=str(account.get("server") or "unknown"),
            account_mode=str(account.get("trade_mode", "unknown")),
            package_version=str(mt5_module.__version__),
            terminal_build=getattr(terminal, "build", None),
        )
        unit.update(
            status="VALIDATED",
            raw_sha256=metadata["raw_sha256"],
            normalized_sha256=metadata["normalized_sha256"],
            tick_count=metadata["quality"]["tick_count"],
        )
    except Exception as error:
        unit.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        _atomic_json(manifest_path, manifest)
        raise
    _atomic_json(manifest_path, manifest)
    return unit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)