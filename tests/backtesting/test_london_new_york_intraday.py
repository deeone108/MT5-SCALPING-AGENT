from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting.london_new_york_intraday import (
    LondonNewYorkIntradayConfig,
    LondonNewYorkIntradayContinuationStrategy,
)
from mt5_scalping_agent.domain import TradeDirection


def _frame(local_date: date = date(2023, 7, 10), direction: int = 1) -> pd.DataFrame:
    start = pd.Timestamp(f"{local_date.isoformat()} 06:00", tz="Europe/London")
    times = pd.date_range(start, periods=301, freq="min").tz_convert("UTC")
    base, previous = 1.1000, 1.1000
    rows: list[dict[str, object]] = []
    for index, timestamp in enumerate(times[:240], start=1):
        close = base + direction * 0.0060 * index / 240
        rows.append({"time": timestamp, "open": previous, "high": max(previous, close), "low": min(previous, close), "close": close, "tick_volume": 10})
        previous = close
    # A 23-pip pullback from the 60-pip impulse, then a 54-pip reclaim.
    for index, timestamp in enumerate(times[240:], start=1):
        displacement = -0.0023 * min(index, 30) / 30 if index <= 30 else -0.0023 + 0.0017 * (index - 30) / 31
        close = base + direction * (0.0060 + displacement)
        rows.append({"time": timestamp, "open": previous, "high": max(previous, close), "low": min(previous, close), "close": close, "tick_volume": 10})
        previous = close
    return pd.DataFrame(rows)


def _strategy(**kwargs: float) -> LondonNewYorkIntradayContinuationStrategy:
    return LondonNewYorkIntradayContinuationStrategy(spread_points=kwargs.pop("spread_points", 1.0), all_in_cost_pips=kwargs.pop("all_in_cost_pips", 0.6), config=LondonNewYorkIntradayConfig(**kwargs))


def test_qualifying_buy_emits_one_intraday_intent() -> None:
    strategy = _strategy()
    intent = strategy(_frame())

    assert intent is not None
    assert intent.direction is TradeDirection.BUY
    assert intent.target_reward_risk_multiple == 2.0
    assert intent.maximum_holding_duration.total_seconds() == 300 * 60
    assert strategy.diagnostics.emitted_signal_count == 1


def test_qualifying_sell_is_mirrored() -> None:
    intent = _strategy()(_frame(direction=-1))
    assert intent is not None
    assert intent.direction is TradeDirection.SELL


def test_cost_gate_rejects_without_emitting() -> None:
    strategy = _strategy(all_in_cost_pips=1.0)
    assert strategy(_frame()) is None
    assert strategy.diagnostics.rejected_setup_counts["cost_gate"] == 1


def test_london_clock_uses_dst() -> None:
    assert str(_frame(date(2023, 1, 9))["time"].iloc[-1]) == "2023-01-09 11:00:00+00:00"
    assert str(_frame(date(2023, 7, 10))["time"].iloc[-1]) == "2023-07-10 10:00:00+00:00"
