"""Resumably import one validated annual Dukascopy M1 archive.

This is read-only network ingestion. It never connects to MT5 or submits orders.
Each invocation fetches a bounded number of missing calendar chunks; the annual
file is created atomically only after every chunk has been validated.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Sequence

import pandas as pd

from mt5_scalping_agent.data import DukascopyDataError, DukascopyM1Client
from mt5_scalping_agent.data.validation import validate_ohlcv


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumably import one annual Dukascopy M1 archive.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "dukascopy_annual")
    parser.add_argument("--chunk-days", type=int, default=14)
    parser.add_argument("--max-chunks", type=int, default=8)
    return parser.parse_args(arguments)


def chunk_bounds(year: int, chunk_days: int) -> tuple[tuple[datetime, datetime], ...]:
    if not 2000 <= year <= 2100 or not 1 <= chunk_days <= 20:
        raise ValueError("year or chunk-days is outside supported bounds")
    start, end = datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)
    bounds: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + timedelta(days=chunk_days), end)
        bounds.append((cursor, next_cursor))
        cursor = next_cursor
    return tuple(bounds)


def _chunk_path(root: Path, symbol: str, start: datetime, end: datetime) -> Path:
    return root / f"{symbol}_m1_{start:%Y%m%d}_{end:%Y%m%d}.csv.gz"


def _empty_marker_path(root: Path, symbol: str, start: datetime, end: datetime) -> Path:
    return root / f"{symbol}_m1_{start:%Y%m%d}_{end:%Y%m%d}.empty.json"


def _read_valid_chunk(path: Path, start: datetime, end: datetime) -> pd.DataFrame:
    frame = pd.read_csv(path, compression="gzip")
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="raise")
    validated = validate_ohlcv(frame).reset_index(drop=True)
    if (validated["time"] < start).any() or (validated["time"] >= end).any():
        raise ValueError(f"chunk contains timestamps outside its interval: {path}")
    return validated


def _write_atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        frame.to_csv(temporary, index=False, compression="gzip")
        _read_valid_chunk(temporary, frame["time"].iloc[0].to_pydatetime(), frame["time"].iloc[-1].to_pydatetime() + timedelta(minutes=1))
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def import_annual(client: DukascopyM1Client, symbol: str, year: int, output_dir: Path, *, chunk_days: int = 14, max_chunks: int = 8) -> dict[str, object]:
    if max_chunks <= 0:
        raise ValueError("max-chunks must be positive")
    normalized = symbol.upper()
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = output_dir / "chunks" / normalized / str(year)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    fetched = 0
    chunks: list[dict[str, object]] = []
    for start, end in chunk_bounds(year, chunk_days):
        path = _chunk_path(chunk_dir, normalized, start, end)
        empty_marker = _empty_marker_path(chunk_dir, normalized, start, end)
        if empty_marker.exists():
            marker = json.loads(empty_marker.read_text(encoding="utf-8"))
            if marker != {"start": start.isoformat(), "end": end.isoformat(), "reason": "no_bars_returned"}:
                raise ValueError(f"empty chunk marker does not match its interval: {empty_marker}")
            chunks.append({"path": str(empty_marker), "start": start.isoformat(), "end": end.isoformat(), "rows": 0, "status": "empty"})
            continue
        if path.exists():
            frame = _read_valid_chunk(path, start, end)
            chunks.append({"path": str(path), "start": start.isoformat(), "end": end.isoformat(), "rows": len(frame), "status": "existing"})
            continue
        if fetched >= max_chunks:
            chunks.append({"path": str(path), "start": start.isoformat(), "end": end.isoformat(), "rows": None, "status": "pending"})
            continue
        try:
            frame = client.historical_ohlcv(normalized, start, end)
        except DukascopyDataError as error:
            if "No Dukascopy M1 bars returned" in str(error):
                empty_marker.write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "reason": "no_bars_returned"}), encoding="utf-8")
                fetched += 1
                chunks.append({"path": str(empty_marker), "start": start.isoformat(), "end": end.isoformat(), "rows": 0, "status": "empty"})
                continue
            raise DukascopyDataError(f"chunk {start.isoformat()} to {end.isoformat()} failed: {error}") from error
        _write_atomic_csv(frame, path)
        fetched += 1
        chunks.append({"path": str(path), "start": start.isoformat(), "end": end.isoformat(), "rows": len(frame), "status": "downloaded"})
    complete = all(item["status"] != "pending" for item in chunks)
    result: dict[str, object] = {"symbol": normalized, "year": year, "chunk_days": chunk_days, "fetched_this_run": fetched, "complete": complete, "chunks": chunks}
    if complete:
        frames = [_read_valid_chunk(Path(str(item["path"])), datetime.fromisoformat(str(item["start"])), datetime.fromisoformat(str(item["end"]))) for item in chunks if item["status"] != "empty"]
        annual = validate_ohlcv(pd.concat(frames, ignore_index=True)).reset_index(drop=True)
        annual_path = output_dir / f"{normalized}_m1_{year}.csv.gz"
        _write_atomic_csv(annual, annual_path)
        result["annual_path"] = str(annual_path)
        result["annual_rows"] = len(annual)
    manifest = output_dir / f"{normalized}_m1_{year}_resumable_manifest.json"
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["manifest_path"] = str(manifest)
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    result = import_annual(DukascopyM1Client(), args.symbol, args.year, args.output_dir, chunk_days=args.chunk_days, max_chunks=args.max_chunks)
    print(json.dumps({key: value for key, value in result.items() if key != "chunks"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
