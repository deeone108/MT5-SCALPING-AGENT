from datetime import UTC

import pandas as pd

from mt5_scalping_agent.backtesting.efficient_trend_scalper import EfficientTrendScalperBacktestStrategy
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
        return SignalProposal(symbol=market.symbol, direction=TradeDirection.NO_TRADE, strategy="recording", generated_at=market.observed_at)


def test_uses_exact_m1_row_and_latest_completed_m5_row() -> None:
    recording = RecordingStrategy()
    m1 = ohlcv("2026-01-05 07:00", 40, "min")
    m5 = ohlcv("2026-01-05 07:00", 40, "5min")
    adapter = EfficientTrendScalperBacktestStrategy("EURUSD", m1, m5, 0.0001, strategy=recording)

    assert adapter(m1.iloc[[34]]) is None
    assert recording.market is not None
    assert len(recording.market.m1) == 1
    assert recording.market.m1["time"].iloc[0] == pd.Timestamp("2026-01-05 07:34", tz="UTC")
    assert recording.market.m5["time"].iloc[0] == pd.Timestamp("2026-01-05 07:30", tz="UTC")
