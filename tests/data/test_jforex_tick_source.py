from pathlib import Path

import pandas as pd
import pytest

from mt5_scalping_agent.data.jforex_tick_source import JForexTickError, import_jforex_ticks


def write_export(path: Path, ask: float = 1.1002) -> Path:
    path.write_text(
        "timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n"
        f"1546819200123,EURUSD,1.1000,{ask},1.5,2.5,0\n"
        "1546819200123,EURUSD,1.1001,1.1003,1.4,2.4,1\n",
        encoding="utf-8",
    )
    return path


def test_import_preserves_bid_ask_utc_milliseconds_and_same_time_order(tmp_path: Path) -> None:
    source = write_export(tmp_path / "pilot.csv")
    result = import_jforex_ticks(source, tmp_path / "ticks")
    frame = pd.read_parquet(result["normalized_path"])

    assert frame["timestamp_utc_ns"].iloc[0] == 1546819200123000000
    assert frame[["bid", "ask"]].values.tolist() == [[1.1, 1.1002], [1.1001, 1.1003]]
    assert frame["source_sequence"].tolist() == [0, 1]
    assert Path(result["raw_path"]).read_bytes() == source.read_bytes()
    assert Path(tmp_path / "ticks/manifests/jforex_import.json").is_file()


def test_import_rejects_crossed_quote(tmp_path: Path) -> None:
    with pytest.raises(JForexTickError, match="crossed"):
        import_jforex_ticks(write_export(tmp_path / "bad.csv", ask=1.0999), tmp_path / "ticks")
