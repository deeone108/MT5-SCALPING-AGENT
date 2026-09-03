from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pandas as pd

from mt5_scalping_agent.data import DukascopyDataError


MODULE_PATH = Path("scripts/import_dukascopy_annual_resumable.py")
SPEC = importlib.util.spec_from_file_location("resumable_import", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Client:
    def historical_ohlcv(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        assert symbol == "GBPUSD"
        return pd.DataFrame({
            "time": pd.to_datetime([start]),
            "open": [1.2], "high": [1.3], "low": [1.1], "close": [1.25], "tick_volume": [1.0],
        })


def test_resumes_chunks_and_only_assembles_when_complete(tmp_path: Path) -> None:
    first = MODULE.import_annual(Client(), "GBPUSD", 2020, tmp_path, chunk_days=20, max_chunks=1)
    assert first["fetched_this_run"] == 1
    assert first["complete"] is False
    assert not (tmp_path / "GBPUSD_m1_2020.csv.gz").exists()

    completed = MODULE.import_annual(Client(), "GBPUSD", 2020, tmp_path, chunk_days=20, max_chunks=30)
    assert completed["complete"] is True
    assert completed["annual_rows"] == len(MODULE.chunk_bounds(2020, 20))
    assert (tmp_path / "GBPUSD_m1_2020.csv.gz").is_file()


class EmptyFinalChunkClient(Client):
    def historical_ohlcv(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        if start.month == 12 and start.day == 26:
            raise DukascopyDataError("No Dukascopy M1 bars returned for requested range")
        return super().historical_ohlcv(symbol, start, end)


def test_records_empty_market_chunk_and_assembles_remaining_data(tmp_path: Path) -> None:
    result = MODULE.import_annual(
        EmptyFinalChunkClient(), "GBPUSD", 2020, tmp_path, chunk_days=20, max_chunks=30
    )

    assert result["complete"] is True
    assert result["annual_rows"] == len(MODULE.chunk_bounds(2020, 20)) - 1
    assert result["chunks"][-1]["status"] == "empty"
    assert Path(str(result["chunks"][-1]["path"])).is_file()