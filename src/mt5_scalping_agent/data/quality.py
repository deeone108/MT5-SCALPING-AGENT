"""M1 archive quality diagnostics that preserve uncertainty about absent quotes."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
from typing import Any

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.sessions import session_name
from mt5_scalping_agent.data.validation import PRICE_COLUMNS, REQUIRED_OHLCV_COLUMNS


@dataclass(frozen=True)
class ProviderProvenance:
    """Human-auditable identity and time semantics for an archive segment."""

    provider: str
    source: str
    time_basis: str
    accepted_period: str
    status: str = "accepted"


HISTDATA_PROVENANCE = ProviderProvenance(
    provider="histdata",
    source="HistData Generic ASCII M1 bid bars",
    time_basis="fixed EST normalized to UTC; not DST-equivalent to New York local time",
    accepted_period="through 2018-12-31",
)
DUKASCOPY_PROVENANCE = ProviderProvenance(
    provider="dukascopy",
    source="Dukascopy public bid-side M1 feed",
    time_basis="UTC",
    accepted_period="from 2019-01-01",
)


@dataclass(frozen=True)
class M1DataQualityReport:
    """Serializable quality statistics for one explicit half-open UTC period."""

    provider_provenance: dict[str, str]
    period_start: str
    period_end: str
    calendar_minutes: int
    expected_minutes: int
    scheduled_closed_minutes: int
    observed_rows: int
    observed_minutes: int
    observed_expected_minutes: int
    observed_outside_expected_minutes: int
    missing_minutes: int
    possible_no_tick_minutes: int
    unexplained_missing_minutes: int
    duplicate_timestamps: int
    malformed_timestamps: int
    off_grid_timestamps: int
    malformed_ohlc: int
    invalid_volumes: int
    zero_volume_rows: int
    gap_count: int
    possible_no_tick_gap_count: int
    longest_data_gap_minutes: int
    longest_data_gap_start: str | None
    longest_data_gap_end: str | None
    gaps_by_session: dict[str, int]
    gaps_by_date: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_m1_frame(
    frame: pd.DataFrame,
    start: datetime,
    end: datetime,
    provenance: ProviderProvenance,
    *,
    possible_no_tick_gap_limit: int = 2,
) -> M1DataQualityReport:
    """Audit raw M1 rows without presenting uncertain missing bars as corruption.

    `expected_minutes` follows the continuously traded FX week from Sunday 17:00
    through Friday 17:00 America/New_York. Holidays are not inferred. Short,
    bounded gaps are labelled *possible* no-tick intervals; the source data alone
    cannot prove why a quote is absent.
    """
    normalized_start, normalized_end = _validate_period(start, end)
    if possible_no_tick_gap_limit < 0:
        raise ValueError("possible_no_tick_gap_limit cannot be negative")
    missing_columns = REQUIRED_OHLCV_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"M1 data is missing columns: {sorted(missing_columns)}")

    parsed_time = pd.to_datetime(frame["time"], utc=True, errors="coerce", format="mixed")
    valid_time = parsed_time.dropna()
    aligned = valid_time.dt.floor("min") == valid_time
    in_period = (valid_time >= pd.Timestamp(normalized_start)) & (valid_time < pd.Timestamp(normalized_end))
    usable_time = valid_time.loc[aligned & in_period]
    observed = pd.DatetimeIndex(usable_time.unique()).sort_values()

    calendar = pd.date_range(normalized_start, normalized_end, freq="min", inclusive="left")
    expected = calendar[_forex_week_mask(calendar)]
    observed_expected = expected.intersection(observed)
    missing = expected.difference(observed)
    observed_outside = observed.difference(expected)
    gaps = _contiguous_gaps(missing)
    observed_set = set(observed)
    possible_gaps = [
        gap
        for gap in gaps
        if len(gap) <= possible_no_tick_gap_limit
        and gap[0] - pd.Timedelta(1, unit="min") in observed_set
        and gap[-1] + pd.Timedelta(1, unit="min") in observed_set
    ]
    possible_minutes = sum(len(gap) for gap in possible_gaps)
    longest = max(gaps, key=len, default=None)

    session_counts = Counter(
        session_name(timestamp.to_pydatetime()) for timestamp in missing
    )
    date_counts = Counter(timestamp.date().isoformat() for timestamp in missing)
    malformed_ohlc, invalid_volumes, zero_volume_rows = _invalid_value_counts(frame)

    return M1DataQualityReport(
        provider_provenance=asdict(provenance),
        period_start=normalized_start.isoformat(),
        period_end=normalized_end.isoformat(),
        calendar_minutes=len(calendar),
        expected_minutes=len(expected),
        scheduled_closed_minutes=len(calendar) - len(expected),
        observed_rows=len(frame),
        observed_minutes=len(observed),
        observed_expected_minutes=len(observed_expected),
        observed_outside_expected_minutes=len(observed_outside),
        missing_minutes=len(missing),
        possible_no_tick_minutes=possible_minutes,
        unexplained_missing_minutes=len(missing) - possible_minutes,
        duplicate_timestamps=int(len(valid_time) - valid_time.nunique()),
        malformed_timestamps=int(parsed_time.isna().sum()),
        off_grid_timestamps=int((~aligned).sum()),
        malformed_ohlc=malformed_ohlc,
        invalid_volumes=invalid_volumes,
        zero_volume_rows=zero_volume_rows,
        gap_count=len(gaps),
        possible_no_tick_gap_count=len(possible_gaps),
        longest_data_gap_minutes=len(longest) if longest is not None else 0,
        longest_data_gap_start=longest[0].isoformat() if longest is not None else None,
        longest_data_gap_end=longest[-1].isoformat() if longest is not None else None,
        gaps_by_session=dict(sorted(session_counts.items())),
        gaps_by_date=dict(sorted(date_counts.items())),
    )


def archive_provenance_inventory(root: Path, symbol: str = "EURUSD") -> dict[str, Any]:
    """Inventory provider files while keeping the 2019 boundary authoritative."""
    normalized_symbol = symbol.upper()
    histdata_dir = root / "histdata"
    dukascopy_dir = root / "dukascopy_annual"
    histdata_files = _year_files(histdata_dir, normalized_symbol)
    dukascopy_files = _year_files(dukascopy_dir, normalized_symbol)
    post_boundary_manifests = [
        _manifest_record(path)
        for path in sorted(histdata_dir.glob(f"{normalized_symbol}_m1_*_manifest.json"))
        if (_manifest_start_year(path, normalized_symbol) or 0) >= 2019
    ]
    return {
        "provider_boundary_utc": "2019-01-01T00:00:00+00:00",
        "boundary_policy": "HistData through 2018; Dukascopy from 2019; cross-boundary loads rejected",
        "histdata": {
            "provenance": asdict(HISTDATA_PROVENANCE),
            "accepted_files": [str(path) for year, path in histdata_files.items() if year <= 2018],
            "out_of_policy_files": [str(path) for year, path in histdata_files.items() if year >= 2019],
            "post_boundary_manifests": post_boundary_manifests,
        },
        "dukascopy": {
            "provenance": asdict(DUKASCOPY_PROVENANCE),
            "accepted_files": [str(path) for year, path in dukascopy_files.items() if year >= 2019],
            "out_of_policy_files": [str(path) for year, path in dukascopy_files.items() if year <= 2018],
        },
    }


def _validate_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    normalized_start, normalized_end = start.astimezone(UTC), end.astimezone(UTC)
    if normalized_start >= normalized_end:
        raise ValueError("start must be before end")
    if normalized_start.second or normalized_start.microsecond or normalized_end.second or normalized_end.microsecond:
        raise ValueError("audit period bounds must be minute-aligned")
    return normalized_start, normalized_end


def _forex_week_mask(index: pd.DatetimeIndex) -> np.ndarray:
    new_york = index.tz_convert("America/New_York")
    minute = new_york.hour * 60 + new_york.minute
    weekday = new_york.dayofweek
    return np.asarray(
        ((weekday >= 0) & (weekday <= 3))
        | ((weekday == 4) & (minute < 17 * 60))
        | ((weekday == 6) & (minute >= 17 * 60)),
        dtype=bool,
    )


def _contiguous_gaps(missing: pd.DatetimeIndex) -> list[pd.DatetimeIndex]:
    if missing.empty:
        return []
    breaks = (np.flatnonzero(np.diff(missing.asi8) != pd.Timedelta(1, unit="min").value) + 1).tolist()
    starts, ends = [0, *breaks], [*breaks, len(missing)]
    return [missing[start:end] for start, end in zip(starts, ends)]


def _invalid_value_counts(frame: pd.DataFrame) -> tuple[int, int, int]:
    prices = frame[list(PRICE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    finite_positive = np.isfinite(prices).all(axis=1) & (prices > 0).all(axis=1)
    geometry = (
        (prices["high"] >= prices[["open", "close", "low"]].max(axis=1))
        & (prices["low"] <= prices[["open", "close", "high"]].min(axis=1))
    )
    malformed_ohlc = int((~(finite_positive & geometry)).sum())

    volumes = pd.to_numeric(frame["tick_volume"], errors="coerce")
    finite_volume = np.isfinite(volumes)
    valid_volume = finite_volume & (volumes >= 0)
    zero_volume = finite_volume & (volumes == 0)
    return malformed_ohlc, int((~valid_volume).sum()), int(zero_volume.sum())


def _year_files(directory: Path, symbol: str) -> dict[int, Path]:
    files: dict[int, Path] = {}
    for path in sorted(directory.glob(f"{symbol}_m1_*.csv.gz")):
        suffix = path.name.removeprefix(f"{symbol}_m1_").removesuffix(".csv.gz")
        if suffix.isdigit() and len(suffix) == 4:
            files[int(suffix)] = path
    return files

def _manifest_start_year(path: Path, symbol: str) -> int | None:
    suffix = path.name.removeprefix(f"{symbol}_m1_").removesuffix("_manifest.json")
    first = suffix.split("_", maxsplit=1)[0]
    return int(first) if first.isdigit() and len(first) == 4 else None


def _manifest_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "readable": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return record
    failures = payload.get("failures", [])
    files = payload.get("files", [])
    record.update({
        "readable": True,
        "reported_file_count": len(files) if isinstance(files, list) else None,
        "failures": failures if isinstance(failures, list) else [],
        "status": "rejected" if failures and not files else "requires_review",
    })
    return record
