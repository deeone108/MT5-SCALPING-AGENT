from datetime import UTC

import pandas as pd

from mt5_scalping_agent.backtesting.trend_scalper import TrendScalperBacktestStrategy
from mt5_scalping_agent.domain import SignalProposal, TradeDirection


def ohlcv(start: str, periods: int, frequency: str) -> pd.DataFrame:
    close = [1.1000 + index * 0.0001 for index in range(periods)]
    return pd.DataFrame(
        {
            "time": pd.date_range(start, periods=periods, freq=frequency, tz=UTC),
            "open": close,
            "high": [value + 0.0002 for value in close],
            "low": [value - 0.0002 for value in close],
            "close": close,
            "tick_volume": [10] * periods,
        }
    )


class RecordingStrategy:
    def __init__(self) -> None:
        self.market = None

    def propose(self, market):  # type: ignore[no-untyped-def]
        self.market = market
        return SignalProposal(
            symbol=market.symbol,
            direction=TradeDirection.NO_TRADE,
            strategy="recording",
            generated_at=market.observed_at,
        )


def test_adapter_exposes_only_m5_candles_closed_by_m1_close() -> None:
    recording = RecordingStrategy()
    m5 = ohlcv("2026-01-05 07:00", 40, "5min")
    adapter = TrendScalperBacktestStrategy("EURUSD", m5, point=0.0001, strategy=recording)
    m1_history = ohlcv("2026-01-05 07:00", 35, "min")

    assert adapter(m1_history) is None
    assert recording.market is not None
    assert recording.market.observed_at == pd.Timestamp("2026-01-05 07:35", tz="UTC").to_pydatetime()
    assert recording.market.m5["time"].iloc[-1] == pd.Timestamp("2026-01-05 07:30", tz="UTC")
    assert len(recording.market.m5) == 7


def test_adapter_waits_for_the_first_completed_m5_candle() -> None:
    recording = RecordingStrategy()
    adapter = TrendScalperBacktestStrategy("EURUSD", ohlcv("2026-01-05 07:00", 40, "5min"), point=0.0001, strategy=recording)

    assert adapter(ohlcv("2026-01-05 07:00", 4, "min")) is None
    assert recording.market is None
