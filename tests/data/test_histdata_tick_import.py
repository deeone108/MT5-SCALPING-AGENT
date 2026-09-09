import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from mt5_scalping_agent.data.histdata_tick_source import HistDataTickSource


def test_import_preserves_raw_and_roundtrips_zstd_parquet(tmp_path: Path) -> None:
    incoming = tmp_path / "provider-name.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "DAT_ASCII_USDJPY_T_201901.csv",
            "20190107 120000000,108.10,108.12,0\n20190107 120000000,108.11,108.13,0\n",
        )
    incoming.write_bytes(buffer.getvalue())

    result = HistDataTickSource().import_archive(incoming, tmp_path / "ticks")
    frame = pd.read_parquet(result["normalized_path"])

    assert Path(result["raw_path"]).read_bytes() == incoming.read_bytes()
    assert frame["source_sequence"].tolist() == [0, 1]
    assert frame["spread_pips"].tolist() == pytest.approx([2.0, 2.0])
    assert result["ticks"] == 2
