"""Generate a read-only M1 archive quality and provenance report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from mt5_scalping_agent.data.quality import (
    DUKASCOPY_PROVENANCE,
    HISTDATA_PROVENANCE,
    ProviderProvenance,
    archive_provenance_inventory,
    audit_m1_frame,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("reports/data_quality/eurusd_m1_archive_audit.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(UTC)
    inventory = archive_provenance_inventory(args.root, args.symbol)
    file_reports: list[dict[str, Any]] = []
    providers = (
        ("histdata", HISTDATA_PROVENANCE),
        ("dukascopy", DUKASCOPY_PROVENANCE),
    )
    for provider, provenance in providers:
        for raw_path in inventory[provider]["accepted_files"]:
            path = Path(raw_path)
            year = int(path.name.removeprefix(f"{args.symbol.upper()}_m1_").removesuffix(".csv.gz"))
            frame = pd.read_csv(path, compression="gzip")
            start = datetime(year, 1, 1, tzinfo=UTC)
            end, partial = _audit_end(frame, year, generated_at)
            report = audit_m1_frame(frame, start, end, provenance)
            file_reports.append({
                "path": str(path),
                "year": year,
                "partial_period": partial,
                **report.to_dict(),
            })
            print(
                f"audited {path}: observed={report.observed_minutes} "
                f"missing_expected={report.missing_minutes} duplicates={report.duplicate_timestamps}",
                flush=True,
            )

    payload = {
        "generated_at": generated_at.isoformat(),
        "symbol": args.symbol.upper(),
        "methodology": {
            "period_semantics": "half-open UTC minute ranges",
            "expected_market_week": "Sunday 17:00 through Friday 17:00 America/New_York; holidays not inferred",
            "possible_no_tick_rule": "one- or two-minute active-market gap bounded by observed adjacent minutes",
            "uncertainty_warning": (
                "possible_no_tick is a heuristic, not proof; all other active-market absences remain "
                "unexplained rather than being labelled corrupt"
            ),
            "m5_safety": (
                "resample_m1_to_m5 excludes incomplete constituent buckets by default and exposes "
                "m1_count/is_complete plus dropped-bucket metadata"
            ),
        },
        "inventory": inventory,
        "summary": _aggregate(file_reports),
        "files": file_reports,
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.report_path}", flush=True)
    return 0


def _audit_end(frame: pd.DataFrame, year: int, now: datetime) -> tuple[datetime, bool]:
    full_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    if year != now.year:
        return full_end, False
    parsed = pd.to_datetime(frame["time"], utc=True, errors="coerce", format="mixed").dropna()
    if parsed.empty:
        return full_end, False
    last_observation_end = parsed.max().floor("min").to_pydatetime() + timedelta(minutes=1)
    return min(full_end, last_observation_end), last_observation_end < full_end


def _aggregate(file_reports: list[dict[str, Any]]) -> dict[str, Any]:
    additive = (
        "calendar_minutes",
        "expected_minutes",
        "scheduled_closed_minutes",
        "observed_rows",
        "observed_minutes",
        "observed_expected_minutes",
        "observed_outside_expected_minutes",
        "missing_minutes",
        "possible_no_tick_minutes",
        "unexplained_missing_minutes",
        "duplicate_timestamps",
        "malformed_timestamps",
        "off_grid_timestamps",
        "malformed_ohlc",
        "invalid_volumes",
        "zero_volume_rows",
        "gap_count",
        "possible_no_tick_gap_count",
    )
    totals = {field: sum(int(report[field]) for report in file_reports) for field in additive}
    sessions: Counter[str] = Counter()
    for report in file_reports:
        sessions.update(report["gaps_by_session"])
    longest = max(file_reports, key=lambda report: report["longest_data_gap_minutes"], default=None)
    totals.update({
        "file_count": len(file_reports),
        "gaps_by_session": dict(sorted(sessions.items())),
        "longest_data_gap": None if longest is None else {
            "path": longest["path"],
            "minutes": longest["longest_data_gap_minutes"],
            "start": longest["longest_data_gap_start"],
            "end": longest["longest_data_gap_end"],
        },
    })
    return totals


if __name__ == "__main__":
    raise SystemExit(main())
