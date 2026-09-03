from datetime import UTC, datetime

import pandas as pd
import pytest

from mt5_scalping_agent.data.local_archive import LocalArchiveError, LocalResearchArchive, resample_m1_to_m5


def _write_annual(root, directory: str, year: int, rows: list[dict[str, object]]) -> None:  # type: ignore[no-untyped-def]
    path = root / directory
    path.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(path / f"EURUSD_m1_{year}.csv.gz", index=False, compression="gzip")


def _rows(times: list[str]) -> list[dict[str, object]]:
    return [
        {"time": timestamp, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "tick_volume": 1}
        for timestamp in times
    ]


def test_load_m1_reads_only_requested_single_provider_window(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_annual(tmp_path, "dukascopy_annual", 2020, _rows(["2020-01-02T00:00:00Z", "2020-01-02T00:01:00Z"]))

    loaded = LocalResearchArchive(tmp_path).load_m1(
        "EURUSD", datetime(2020, 1, 2, tzinfo=UTC), datetime(2020, 1, 2, 0, 1, tzinfo=UTC)
    )

    assert loaded["time"].tolist() == [pd.Timestamp("2020-01-02T00:00:00Z")]


def test_load_m1_rejects_provider_boundary_crossing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(LocalArchiveError, match="provider boundary"):
        LocalResearchArchive(tmp_path).load_m1(
            "EURUSD", datetime(2018, 12, 31, tzinfo=UTC), datetime(2019, 1, 2, tzinfo=UTC)
        )


def test_resample_m1_to_m5_preserves_ohlcv_aggregation() -> None:
    m1 = pd.DataFrame({
        "time": pd.date_range("2020-01-02T00:00:00Z", periods=5, freq="min"),
        "open": [1.0, 1.1, 1.2, 1.3, 1.4], "high": [1.1, 1.2, 1.3, 1.4, 1.5],
        "low": [0.9, 1.0, 1.1, 1.2, 1.3], "close": [1.05, 1.15, 1.25, 1.35, 1.45],
        "tick_volume": [1, 2, 3, 4, 5],
    })

    m5 = resample_m1_to_m5(m1)

    assert len(m5) == 1
    assert m5.iloc[0].to_dict() == {
        "time": pd.Timestamp("2020-01-02T00:00:00Z"), "open": 1.0, "high": 1.5,
        "low": 0.9, "close": 1.45, "tick_volume": 15,
        "m1_count": 5, "is_complete": True,
    }
    assert m5.attrs["incomplete_m5_bars"] == 0


def test_resample_m1_to_m5_drops_and_reports_incomplete_buckets_by_default() -> None:
    m1 = pd.DataFrame({
        "time": pd.date_range("2020-01-02T00:00:00Z", periods=6, freq="min"),
        "open": [1.0] * 6, "high": [1.1] * 6, "low": [0.9] * 6,
        "close": [1.0] * 6, "tick_volume": [1] * 6,
    })

    m5 = resample_m1_to_m5(m1)

    assert m5["time"].tolist() == [pd.Timestamp("2020-01-02T00:00:00Z")]
    assert m5["is_complete"].tolist() == [True]
    assert m5.attrs["incomplete_m5_bars"] == 1
    assert m5.attrs["incomplete_m5_examples"] == [
        {"time": "2020-01-02T00:05:00+00:00", "m1_count": 1}
    ]


def test_resample_m1_to_m5_can_keep_flagged_or_reject_incomplete_buckets() -> None:
    m1 = pd.DataFrame({
        "time": pd.date_range("2020-01-02T00:00:00Z", periods=6, freq="min"),
        "open": [1.0] * 6, "high": [1.1] * 6, "low": [0.9] * 6,
        "close": [1.0] * 6, "tick_volume": [1] * 6,
    })

    kept = resample_m1_to_m5(m1, incomplete="keep")

    assert kept["m1_count"].tolist() == [5, 1]
    assert kept["is_complete"].tolist() == [True, False]
    with pytest.raises(LocalArchiveError, match="1/5 M1 constituents"):
        resample_m1_to_m5(m1, incomplete="raise")


def test_load_m1_window_ending_at_provider_boundary_does_not_require_next_year(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_annual(tmp_path, "histdata", 2018, _rows(["2018-12-31T23:59:00Z"]))

    loaded = LocalResearchArchive(tmp_path).load_m1(
        "EURUSD", datetime(2018, 12, 31, tzinfo=UTC), datetime(2019, 1, 1, tzinfo=UTC)
    )

    assert len(loaded) == 1

def test_post_boundary_request_never_falls_back_to_ambiguous_histdata_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _write_annual(tmp_path, "histdata", 2019, _rows(["2019-01-02T00:00:00Z"]))

    with pytest.raises(LocalArchiveError, match="dukascopy.*missing annual files"):
        LocalResearchArchive(tmp_path).load_m1(
            "EURUSD", datetime(2019, 1, 2, tzinfo=UTC), datetime(2019, 1, 3, tzinfo=UTC)
        )
