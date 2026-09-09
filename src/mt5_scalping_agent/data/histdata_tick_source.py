"""Offline ingestion of manually downloaded HistData Generic ASCII tick ZIPs."""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from mt5_scalping_agent.data.historical_tick_source import (
    HistoricalTickSource, TickSourceArtifact, TickSourceLicense, TickSourceSchema,
    TickTimestampSemantics,
)

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
PIP_SIZES = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCAD": 0.0001}
FIXED_EST = timezone(timedelta(hours=-5))
MEMBER_PATTERN = re.compile(r"(?:DAT_)?ASCII_([A-Z]{6})_T_?(\d{6})\.csv$", re.IGNORECASE)


class HistDataTickError(RuntimeError):
    """Raised when a native archive is unsafe or not the required tick format."""


@dataclass(frozen=True)
class ParsedHistDataArchive:
    pair: str
    year: int
    month: int
    member: str
    raw_sha256: str
    ticks: pd.DataFrame


class HistDataTickSource(HistoricalTickSource):
    """Local-only adapter; free website downloads remain a human action."""

    @property
    def provider_name(self) -> str:
        return "histdata"

    def list_available(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]:
        _validate_scope(pair, start, end)
        return ()

    def acquire(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]:
        _validate_scope(pair, start, end)
        raise HistDataTickError("manual download required from HistData's Generic ASCII / Tick Data workflow")

    def source_timestamp_semantics(self) -> TickTimestampSemantics:
        return TickTimestampSemantics("milliseconds", "fixed UTC-05:00 (no DST)", True)

    def source_schema(self) -> TickSourceSchema:
        return TickSourceSchema(("DateTime", "Bid", "Ask", "Volume"), True, "provider field; not traded volume", True)

    def licensing_metadata(self) -> TickSourceLicense:
        return TickSourceLicense("free manual website download", False, None, "https://www.histdata.com/")

    def parse_archive(self, path: Path) -> ParsedHistDataArchive:
        payload = path.read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                bad = archive.testzip()
                if bad:
                    raise HistDataTickError(f"ZIP CRC failure in member: {bad}")
                members = [name for name in archive.namelist() if MEMBER_PATTERN.search(Path(name).name)]
                if len(members) != 1:
                    raise HistDataTickError("archive must contain exactly one Generic ASCII tick CSV")
                match = MEMBER_PATTERN.search(Path(members[0]).name)
                assert match is not None
                pair, period = match.group(1).upper(), match.group(2)
                if pair not in PAIRS or not 2019 <= int(period[:4]) <= 2023:
                    raise HistDataTickError("archive pair/year is outside Phase 22 scope")
                raw = pd.read_csv(
                    archive.open(members[0]), header=None,
                    names=["source_time", "bid", "ask", "source_volume"],
                    dtype={"source_time": "string"},
                )
        except (zipfile.BadZipFile, OSError, pd.errors.ParserError) as error:
            raise HistDataTickError("invalid HistData ZIP archive") from error
        ticks = _normalize(raw, pair, path.name)
        return ParsedHistDataArchive(pair, int(period[:4]), int(period[4:]), members[0], hashlib.sha256(payload).hexdigest(), ticks)

    def import_archive(self, path: Path, root: Path = Path("data/ticks")) -> dict[str, object]:
        parsed = self.parse_archive(path)
        unit = Path(parsed.pair) / str(parsed.year) / f"{parsed.month:02d}"
        raw_path = root / "raw" / "histdata" / unit / path.name
        normalized_path = root / "normalized" / "histdata" / unit / "ticks.parquet"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists() and hashlib.sha256(raw_path.read_bytes()).hexdigest() != parsed.raw_sha256:
            raise HistDataTickError("immutable raw destination already exists with different content")
        if not raw_path.exists():
            shutil.copyfile(path, raw_path)
        try:
            parsed.ticks.to_parquet(normalized_path, compression="zstd", index=False)
        except ImportError as error:
            raise HistDataTickError("Parquet support requires pyarrow or fastparquet") from error
        return {
            "pair": parsed.pair, "year": parsed.year, "month": parsed.month,
            "raw_path": str(raw_path), "raw_sha256": parsed.raw_sha256,
            "normalized_path": str(normalized_path),
            "normalized_sha256": hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
            "ticks": len(parsed.ticks),
        }


def _normalize(raw: pd.DataFrame, pair: str, source_file: str) -> pd.DataFrame:
    if raw.empty or raw.isna().any().any():
        raise HistDataTickError("empty or malformed tick rows")
    try:
        local = pd.to_datetime(raw["source_time"], format="%Y%m%d %H%M%S%f", errors="raise")
        bid = pd.to_numeric(raw["bid"], errors="raise").astype(float)
        ask = pd.to_numeric(raw["ask"], errors="raise").astype(float)
        volume = pd.to_numeric(raw["source_volume"], errors="raise").astype(float)
    except (TypeError, ValueError) as error:
        raise HistDataTickError("tick CSV does not match DateTime,Bid,Ask,Volume") from error
    if not ((bid > 0) & (ask > 0) & (ask >= bid)).all():
        raise HistDataTickError("tick CSV contains non-positive or crossed Bid/Ask")
    utc = local.dt.tz_localize(FIXED_EST).dt.tz_convert(UTC)
    sequence = pd.RangeIndex(len(raw), dtype="int64")
    result = pd.DataFrame({
        "timestamp_utc_ns": utc.astype("int64"), "pair": pair, "bid": bid, "ask": ask,
        "source_volume": volume, "source_sequence": sequence, "source_provider": "histdata",
        "source_file": source_file, "raw_row_number": sequence,
    })
    result["mid_price"] = (result["bid"] + result["ask"]) / 2
    result["spread_price"] = result["ask"] - result["bid"]
    result["spread_pips"] = result["spread_price"] / PIP_SIZES[pair]
    return result.sort_values(["timestamp_utc_ns", "source_sequence"], kind="stable").reset_index(drop=True)


def _validate_scope(pair: str, start: datetime, end: datetime) -> None:
    if pair.upper() not in PAIRS or start.tzinfo is None or end.tzinfo is None:
        raise ValueError("request must use a Phase 22 pair and timezone-aware bounds")
    if start >= end or end.astimezone(UTC) > datetime(2024, 1, 1, tzinfo=UTC):
        raise ValueError("request must be ordered and end before 2024")
