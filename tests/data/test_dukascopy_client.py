from datetime import UTC, datetime

import pandas as pd
import pytest

from mt5_scalping_agent.data.dukascopy_client import DukascopyDataError, DukascopyM1Client


def raw_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.1, 1.2],
            "high": [1.2, 1.3],
            "low": [1.0, 1.1],
            "close": [1.15, 1.25],
            "volume": [10.0, 20.0],
        },
        index=pd.DatetimeIndex(["2025-01-06T00:00:00Z", "2025-01-06T00:01:00Z"], name="timestamp"),
    )


def test_normalizes_bid_bars_and_forwards_the_requested_range() -> None:
    calls = []

    def fetcher(*args):  # type: ignore[no-untyped-def]
        calls.append(args)
        return raw_bars()

    start = datetime(2025, 1, 6, tzinfo=UTC)
    end = datetime(2025, 1, 7, tzinfo=UTC)
    result = DukascopyM1Client(fetcher).historical_ohlcv("EURUSD", start, end)

    assert calls[0][0] == "EUR/USD"
    assert len(result) == 2
    assert result["time"].dt.tz is not None
    assert list(result["tick_volume"]) == [10.0, 20.0]


@pytest.mark.parametrize(("symbol", "instrument"), [("GBPUSD", "GBP/USD"), ("USDJPY", "USD/JPY"), ("USDCAD", "USD/CAD")])
def test_supported_cross_pair_symbols_map_to_dukascopy_instruments(symbol: str, instrument: str) -> None:
    calls = []

    def fetcher(*args):  # type: ignore[no-untyped-def]
        calls.append(args)
        return raw_bars()

    DukascopyM1Client(fetcher).historical_ohlcv(
        symbol,
        datetime(2025, 1, 6, tzinfo=UTC),
        datetime(2025, 1, 7, tzinfo=UTC),
    )

    assert calls[0][0] == instrument

def test_rejects_unsupported_symbols_and_empty_responses() -> None:
    client = DukascopyM1Client(lambda *args: pd.DataFrame())
    start = datetime(2025, 1, 6, tzinfo=UTC)
    end = datetime(2025, 1, 7, tzinfo=UTC)

    with pytest.raises(ValueError, match="Unsupported"):
        client.historical_ohlcv("XAUUSD", start, end)
    with pytest.raises(DukascopyDataError, match="No Dukascopy"):
        client.historical_ohlcv("EURUSD", start, end)
