from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError
from mt5_scalping_agent.data.historical_range import MT5HistoricalRangeClient


class FakeRangeMT5:
    def __init__(self) -> None:
        self.range_call = None
        self.rates = np.array(
            [(1_700_000_060, 1.2, 1.3, 1.1, 1.25, 50)],
            dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")],
        )

    def copy_rates_range(self, symbol, timeframe, start, end):  # type: ignore[no-untyped-def]
        self.range_call = (symbol, timeframe, start, end)
        return self.rates

    def last_error(self):
        return (500, "test error")


def test_reads_normalized_explicit_utc_range() -> None:
    terminal = FakeRangeMT5()
    client = MT5HistoricalRangeClient(load_settings({}), terminal)
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, tzinfo=UTC)

    result = client.historical_ohlcv_range("EURUSD", 1, start, end)

    assert terminal.range_call == ("EURUSD", 1, start, end)
    assert result["time"].dt.tz is not None
    assert result["close"].iloc[0] == 1.25


def test_rejects_invalid_or_empty_range() -> None:
    terminal = FakeRangeMT5()
    client = MT5HistoricalRangeClient(load_settings({}), terminal)
    point = datetime(2023, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="earlier"):
        client.historical_ohlcv_range("EURUSD", 1, point, point)

    terminal.rates = None
    with pytest.raises(MT5DataError, match="No historical rates"):
        client.historical_ohlcv_range("EURUSD", 1, point, datetime(2024, 1, 1, tzinfo=UTC))

