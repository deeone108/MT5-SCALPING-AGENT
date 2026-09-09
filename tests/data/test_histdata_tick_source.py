import io
import zipfile
from pathlib import Path

import pytest

from mt5_scalping_agent.data.histdata_tick_source import HistDataTickError, HistDataTickSource, PIP_SIZES


def archive(path: Path, rows: str, member: str = "DAT_ASCII_EURUSD_T_201901.csv") -> Path:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        output.writestr(member, rows)
    path.write_bytes(buffer.getvalue())
    return path


def test_parses_bid_ask_and_fixed_est_in_winter_and_summer(tmp_path: Path) -> None:
    source = HistDataTickSource()
    winter = source.parse_archive(archive(tmp_path / "winter.zip", "20190107 120000000,1.1,1.2,0\n"))
    summer = source.parse_archive(archive(
        tmp_path / "summer.zip", "20190707 120000000,1.3,1.4,0\n", "DAT_ASCII_EURUSD_T_201907.csv"
    ))

    assert winter.ticks["timestamp_utc_ns"].iloc[0] == 1546880400000000000
    assert summer.ticks["timestamp_utc_ns"].iloc[0] == 1562518800000000000
    assert winter.ticks.loc[0, ["bid", "ask"]].tolist() == [1.1, 1.2]


def test_preserves_same_timestamp_source_order_and_rejects_crossed_quote(tmp_path: Path) -> None:
    parsed = HistDataTickSource().parse_archive(archive(
        tmp_path / "ordered.zip",
        "20190107 120000000,1.1,1.2,0\n20190107 120000000,1.2,1.3,0\n",
    ))
    assert parsed.ticks["source_sequence"].tolist() == [0, 1]
    with pytest.raises(HistDataTickError, match="crossed"):
        HistDataTickSource().parse_archive(archive(tmp_path / "bad.zip", "20190107 120000000,1.2,1.1,0\n"))


def test_phase22_pip_sizes_are_complete() -> None:
    assert PIP_SIZES == {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCAD": 0.0001}
