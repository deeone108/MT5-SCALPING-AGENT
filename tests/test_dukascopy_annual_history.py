from datetime import UTC, datetime

import pandas as pd

from scripts.download_dukascopy_annual_history import annual_ohlcv


class Client:
    def iter_historical_ohlcv(self, symbol, start, end, chunk_days):  # type: ignore[no-untyped-def]
        assert symbol == "EURUSD"
        assert start == datetime(2025, 1, 1, tzinfo=UTC)
        assert end == datetime(2026, 1, 1, tzinfo=UTC)
        return iter(
            [
                pd.DataFrame(
                    {
                        "time": pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T00:01:00Z"]),
                        "open": [1.1, 1.1],
                        "high": [1.2, 1.2],
                        "low": [1.0, 1.0],
                        "close": [1.15, 1.15],
                        "tick_volume": [1.0, 2.0],
                    }
                )
            ]
        )


def test_concatenates_and_validates_annual_chunks() -> None:
    result = annual_ohlcv(Client(), "EURUSD", 2025)  # type: ignore[arg-type]

    assert len(result) == 2
    assert result["time"].dt.tz is not None
