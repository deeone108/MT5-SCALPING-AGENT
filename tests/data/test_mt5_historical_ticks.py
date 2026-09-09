from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import os
import pandas as pd
import pytest

from mt5_scalping_agent.data.mt5_historical_ticks import (
    NORMALIZED_FIELDS,
    build_manifest,
    normalize_ticks,
    persist_unit,
    quality_summary,
)

DTYPE = [
    ("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"),
    ("volume", "u8"), ("time_msc", "i8"), ("flags", "u4"), ("volume_real", "f8"),
]


def sample_ticks() -> np.ndarray:
    return np.array(
        [
            (1546300800, 1.10, 1.11, 0.0, 3, 1546300800000, 6, 3.5),
            (1546300800, 1.10, 1.12, 0.0, 4, 1546300800000, 6, 4.5),
            (1548979200, 9.00, 9.10, 0.0, 1, 1548979200000, 2, 1.0),
        ],
        dtype=DTYPE,
    )


def test_manifest_is_monthly_complete_and_development_only(tmp_path: Path) -> None:
    manifest = build_manifest(tmp_path / "manifest.json", tmp_path / "ticks")
    assert len(manifest["units"]) == 240
    assert manifest["units"][0]["start_utc"] == "2019-01-01T00:00:00+00:00"
    assert manifest["units"][-1]["end_utc"] == "2024-01-01T00:00:00+00:00"
    assert {unit["status"] for unit in manifest["units"]} == {"PENDING"}


def test_normalization_is_half_open_and_preserves_same_timestamp_quotes() -> None:
    frame = normalize_ticks(
        sample_ticks(),
        "EURUSD",
        datetime(2019, 1, 1, tzinfo=UTC),
        datetime(2019, 2, 1, tzinfo=UTC),
    )
    assert tuple(frame.columns) == NORMALIZED_FIELDS
    assert len(frame) == 2
    assert frame.source_sequence.tolist() == [0, 1]
    assert frame.timestamp_utc_ns.tolist() == [1546300800000000000] * 2
    assert frame.bid.tolist() == [1.1, 1.1]
    assert frame.ask.tolist() == [1.11, 1.12]
    quality = quality_summary(frame)
    assert quality["duplicate_timestamp_rows"] == 2
    assert quality["same_timestamp_distinct_rows"] == 2


def test_validation_rejects_crossed_quotes_and_nonmonotonic_ticks() -> None:
    ticks = sample_ticks()[:2].copy()
    ticks["ask"][0] = 1.0
    with pytest.raises(ValueError, match="bid/ask"):
        normalize_ticks(ticks, "EURUSD", datetime(2019, 1, 1, tzinfo=UTC), datetime(2019, 2, 1, tzinfo=UTC))
    ticks = sample_ticks()[:2].copy()
    ticks["time_msc"] = ticks["time_msc"][::-1] + np.array([1, 0])
    with pytest.raises(ValueError, match="monotonic"):
        normalize_ticks(ticks, "EURUSD", datetime(2019, 1, 1, tzinfo=UTC), datetime(2019, 2, 1, tzinfo=UTC))


def test_persistence_keeps_exact_raw_array_and_refuses_overwrite(tmp_path: Path) -> None:
    manifest = build_manifest(tmp_path / "manifest.json", tmp_path / "ticks")
    unit = manifest["units"][0]
    raw = sample_ticks()
    metadata = persist_unit(
        raw, unit, broker="RoboForex Ltd", server="RoboForex-ECN", account_mode="demo",
        package_version="5.test", terminal_build="5000",
    )
    with np.load(unit["raw_path"]) as archive:
        np.testing.assert_array_equal(archive["ticks"], raw)
    normalized = pd.read_parquet(unit["normalized_path"])
    assert len(normalized) == 2
    assert metadata["raw_response_rows"] == 3
    assert len(metadata["raw_sha256"]) == 64
    with pytest.raises(FileExistsError, match="overwrite"):
        persist_unit(
            raw, unit, broker="RoboForex Ltd", server="RoboForex-ECN", account_mode="demo",
            package_version="5.test", terminal_build="5000",
        )


def test_downloader_source_contains_no_execution_api() -> None:
    sources = (
        Path("src/mt5_scalping_agent/data/mt5_historical_ticks.py").read_text(encoding="utf-8")
        + Path("scripts/download_mt5_phase22_ticks.py").read_text(encoding="utf-8")
    )
    assert "order_send" not in sources
    assert "positions_" not in sources
    assert "trade_request" not in sources
    assert "copy_ticks_range" in sources

def test_failed_multi_artifact_commit_cleans_current_attempt_for_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = build_manifest(tmp_path / "manifest.json", tmp_path / "ticks")
    unit = manifest["units"][0]
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="interruption"):
        persist_unit(
            sample_ticks(), unit, broker="RoboForex Ltd", server="RoboForex-ECN", account_mode="demo",
            package_version="5.test", terminal_build="5000",
        )
    for key in ("raw_path", "normalized_path", "metadata_path"):
        final = Path(unit[key])
        assert not final.exists()
        assert not final.with_suffix(final.suffix + ".part").exists()