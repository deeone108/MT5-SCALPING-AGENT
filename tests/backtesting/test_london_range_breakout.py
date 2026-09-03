from datetime import UTC

import pandas as pd

from mt5_scalping_agent.backtesting.london_range_breakout import LondonRangeBreakoutStrategy
from mt5_scalping_agent.domain import TradeDirection


def candles(times, highs, lows, closes):
    return pd.DataFrame({"time": pd.to_datetime(times, utc=True), "open": closes, "high": highs, "low": lows, "close": closes, "tick_volume": [1] * len(times)})


def test_emits_one_buy_after_completed_asian_range_break() -> None:
    strategy = LondonRangeBreakoutStrategy()
    data = candles(["2025-01-06T06:59:00Z", "2025-01-06T07:00:00Z", "2025-01-06T07:01:00Z"], [1.11, 1.11, 1.12], [1.09, 1.09, 1.10], [1.10, 1.11, 1.12])

    assert strategy(data.iloc[[0]]) is None
    assert strategy(data.iloc[[1]]) is None
    intent = strategy(data.iloc[[2]])

    assert intent is not None
    assert intent.direction is TradeDirection.BUY
    assert intent.stop_loss == 1.09
    assert strategy(data.iloc[[2]]) is None
