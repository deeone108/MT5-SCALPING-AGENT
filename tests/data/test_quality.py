from datetime import UTC, datetime

import pandas as pd

from mt5_scalping_agent.data.quality import (
    DUKASCOPY_PROVENANCE,
    archive_provenance_inventory,
    audit_m1_frame,
)


def _row(timestamp: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "time": timestamp,
        "open": 1.10,
        "high": 1.11,
        "low": 1.09,
        "close": 1.105,
        "tick_volume": 1,
    }
    row.update(overrides)
    return row


def test_audit_reports_quality_and_preserves_missing_data_uncertainty() -> None:
    frame = pd.DataFrame([
        _row("2025-01-06T08:00:00Z"),
        _row("2025-01-06T08:00:00Z"),
        _row("2025-01-06T08:01:00Z"),
        _row("2025-01-06T08:03:00Z"),
        _row("2025-01-06T08:03:30Z"),
        _row("2025-01-06T08:04:00Z", high=1.08),
        _row("2025-01-06T08:05:00Z", tick_volume=-1),
        _row("2025-01-06T08:08:00Z"),
        _row("not-a-time"),
    ])

    report = audit_m1_frame(
        frame,
        datetime(2025, 1, 6, 8, tzinfo=UTC),
        datetime(2025, 1, 6, 8, 10, tzinfo=UTC),
        DUKASCOPY_PROVENANCE,
    )

    assert report.expected_minutes == 10
    assert report.observed_rows == 9
    assert report.observed_minutes == 6
    assert report.missing_minutes == 4
    assert report.possible_no_tick_minutes == 3
    assert report.unexplained_missing_minutes == 1
    assert report.duplicate_timestamps == 1
    assert report.malformed_timestamps == 1
    assert report.off_grid_timestamps == 1
    assert report.malformed_ohlc == 1
    assert report.invalid_volumes == 1
    assert report.longest_data_gap_minutes == 2
    assert report.gaps_by_session == {"london": 4}
    assert report.gaps_by_date == {"2025-01-06": 4}


def test_audit_excludes_scheduled_weekend_from_expected_minutes() -> None:
    frame = pd.DataFrame([_row("2025-01-04T12:00:00Z")])

    report = audit_m1_frame(
        frame,
        datetime(2025, 1, 4, 12, tzinfo=UTC),
        datetime(2025, 1, 4, 12, 5, tzinfo=UTC),
        DUKASCOPY_PROVENANCE,
    )

    assert report.calendar_minutes == 5
    assert report.expected_minutes == 0
    assert report.scheduled_closed_minutes == 5
    assert report.missing_minutes == 0
    assert report.observed_outside_expected_minutes == 1


def test_inventory_classifies_out_of_policy_files_without_modifying_them(tmp_path) -> None:  # type: ignore[no-untyped-def]
    histdata = tmp_path / "histdata"
    dukascopy = tmp_path / "dukascopy_annual"
    histdata.mkdir()
    dukascopy.mkdir()
    for path in [
        histdata / "EURUSD_m1_2018.csv.gz",
        histdata / "EURUSD_m1_2019.csv.gz",
        histdata / "EURUSD_m1_2019_2019_manifest.json",
        dukascopy / "EURUSD_m1_2018.csv.gz",
        dukascopy / "EURUSD_m1_2019.csv.gz",
    ]:
        path.touch()

    (histdata / "EURUSD_m1_2019_2019_manifest.json").write_text(
        '{"files": [], "failures": [{"year": 2019, "error": "duplicate timestamps"}]}',
        encoding="utf-8",
    )

    inventory = archive_provenance_inventory(tmp_path)

    assert inventory["provider_boundary_utc"] == "2019-01-01T00:00:00+00:00"
    assert inventory["histdata"]["accepted_files"] == [str(histdata / "EURUSD_m1_2018.csv.gz")]
    assert inventory["histdata"]["out_of_policy_files"] == [str(histdata / "EURUSD_m1_2019.csv.gz")]
    assert inventory["histdata"]["post_boundary_manifests"][0]["status"] == "rejected"
    assert inventory["dukascopy"]["out_of_policy_files"] == [str(dukascopy / "EURUSD_m1_2018.csv.gz")]
    assert (histdata / "EURUSD_m1_2019.csv.gz").exists()
