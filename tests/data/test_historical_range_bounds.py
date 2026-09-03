from datetime import UTC, datetime

import numpy as np
import pytest

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError
from mt5_scalping_agent.data.historical_range import MT5HistoricalRangeClient


class FallbackRangeMT5:
    def copy_rates_range(self, symbol, timeframe, start, end):  # type: ignore[no-untyped-def]
        return np.array(
            [(1_700_000_000, 1.0, 1.1, 0.9, 1.0, 1)],
            dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")],
        )

    def last_error(self):
        return (0, "success")


def test_rejects_mt5_fallback_candle_outside_requested_range() -> None:
    client = MT5HistoricalRangeClient(load_settings({}), FallbackRangeMT5())

    with pytest.raises(MT5DataError, match="inside requested range"):
        client.historical_ohlcv_range(
            "EURUSD",
            1,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
        )
