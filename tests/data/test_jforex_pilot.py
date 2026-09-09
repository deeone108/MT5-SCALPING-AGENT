from pathlib import Path

import pytest

from mt5_scalping_agent.data.jforex_pilot import validate_jforex_pilot
from mt5_scalping_agent.data.jforex_tick_source import JForexTickError

HEADER = "timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n"


def write(path: Path, rows: str, newline: bool = True) -> Path:
    path.write_text(HEADER + rows + ("\n" if newline else ""), encoding="utf-8")
    return path


def test_quality_duplicates_and_replay_are_deterministic(tmp_path: Path) -> None:
    rows = ("1546819200123,EURUSD,1.1000,1.1002,1,2,0\n"
            "1546819200123,EURUSD,1.1000,1.1002,1,2,1\n"
            "1546819200123,EURUSD,1.1001,1.1003,1,2,2\n"
            "1546819260124,EURUSD,1.1002,1.1004,1,2,3")
    source = write(tmp_path / "pilot.csv", rows)
    first = validate_jforex_pilot(source, tmp_path / "one")
    second = validate_jforex_pilot(source, tmp_path / "two")
    assert first["exact_duplicate_rows"] == 2
    assert first["same_timestamp_different_quote_rows"] == 1
    assert first["long_gaps_over_60s"] == 1
    assert first["pilot_root_sha256"] == second["pilot_root_sha256"]


@pytest.mark.parametrize(("rows", "message"), [
    ("1546819200000,GBPUSD,1.1,1.2,1,1,0", "EURUSD"),
    ("1546214400000,EURUSD,1.1,1.2,1,1,0", "half-open"),
    ("1547424000000,EURUSD,1.1,1.2,1,1,0", "half-open"),
    ("1546819200000,EURUSD,1.2,1.1,1,1,0", "crossed"),
    ("bad,EURUSD,1.1,1.2,1,1,0", "numeric"),
])
def test_rejects_bad_rows(tmp_path: Path, rows: str, message: str) -> None:
    with pytest.raises(JForexTickError, match=message):
        validate_jforex_pilot(write(tmp_path / "bad.csv", rows), tmp_path / "ticks")


def test_rejects_schema_duplicate_header_missing_and_truncated(tmp_path: Path) -> None:
    bad_schema = tmp_path / "schema.csv"
    bad_schema.write_text("timestamp_utc_ms,pair,bid\n1,EURUSD,1\n", encoding="utf-8")
    with pytest.raises(JForexTickError, match="exact columns"):
        validate_jforex_pilot(bad_schema, tmp_path / "a")
    with pytest.raises(JForexTickError, match="duplicate CSV header"):
        validate_jforex_pilot(write(tmp_path / "header.csv", HEADER.strip()), tmp_path / "b")
    with pytest.raises(JForexTickError, match="pilot file unavailable"):
        validate_jforex_pilot(tmp_path / "absent.csv", tmp_path / "c")
    with pytest.raises(JForexTickError, match="truncated"):
        validate_jforex_pilot(write(tmp_path / "truncated.csv", "1546819200000,EURUSD,1.1,1.2,1,1,0", False), tmp_path / "d")
