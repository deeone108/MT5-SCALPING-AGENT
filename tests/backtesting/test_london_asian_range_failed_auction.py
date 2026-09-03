from __future__ import annotations

from datetime import date

import pandas as pd

from mt5_scalping_agent.backtesting.london_asian_range_failed_auction import (
    LondonAsianRangeFailedAuctionConfig,
    LondonAsianRangeFailedAuctionStrategy,
)
from mt5_scalping_agent.domain import TradeDirection


def _frame(local_date: date = date(2023, 7, 10), sign: int = 1) -> pd.DataFrame:
    times = pd.date_range(f"{local_date} 00:00", f"{local_date} 07:14", freq="min", tz="Europe/London").tz_convert("UTC")
    rows = []
    for timestamp in times:
        local = timestamp.tz_convert("Europe/London").time()
        close, high, low = 1.0995, 1.1000, 1.0990
        if time_in(local, "07:00", "07:04"):
            close, high, low = 1.1008, 1.1010, 1.1000
        elif time_in(local, "07:05", "07:09"):
            close, high, low = 1.1001, 1.1003, 1.1000
        elif time_in(local, "07:10", "07:14"):
            close, high, low = 1.0995, 1.1000, 1.0993
        if sign < 0:
            close, high, low = 2.1990 - close, 2.1990 - low, 2.1990 - high
        rows.append({"time": timestamp, "open": close, "high": high, "low": low, "close": close, "tick_volume": 1.0})
    return pd.DataFrame(rows)


def time_in(value: object, start: str, end: str) -> bool:
    text = value.isoformat(timespec="minutes")
    return start <= text <= end


def _strategy() -> LondonAsianRangeFailedAuctionStrategy:
    return LondonAsianRangeFailedAuctionStrategy(
        spread_points=2.0,
        config=LondonAsianRangeFailedAuctionConfig(
            pip_size=0.0001, stress_cost_pips=1.27, maximum_spread_points=5.0
        ),
    )


def test_upside_sweep_then_inside_range_confirmation_sells() -> None:
    strategy = _strategy()
    intent = strategy(_frame())

    assert intent is not None
    assert intent.direction is TradeDirection.SELL
    assert intent.target_reward_risk_multiple == 2.0


def test_downside_sweep_mirrors_to_buy() -> None:
    assert _strategy()(_frame(sign=-1)).direction is TradeDirection.BUY


def test_emitted_date_cannot_emit_twice() -> None:
    strategy = _strategy()
    assert strategy(_frame()) is not None
    assert strategy(_frame()) is None
    assert strategy.diagnostics["daily_limit"] == 1
