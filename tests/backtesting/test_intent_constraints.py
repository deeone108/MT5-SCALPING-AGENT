from datetime import timedelta

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import (
    BacktestConfig,
    CandleBacktester,
    EntryEconomicsConstraints,
    TradeIntent,
)
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


def _symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=1.0,
        volume_step=0.01,
    )


def _backtester(**costs: float) -> CandleBacktester:
    return CandleBacktester(
        BacktestConfig(initial_balance=10_000, **costs),
        RiskEngine(
            RiskLimits(
                max_lot_size=1.0,
                max_exposure_lots=1.0,
                min_reward_risk_ratio=1.5,
                max_spread_points=10.0,
            )
        ),
        _symbol(),
    )


def _candles(times: pd.DatetimeIndex, *, deadline_hits_target: bool = False) -> pd.DataFrame:
    highs = [1.0002] * len(times)
    if deadline_hits_target:
        highs[-1] = 1.0011
    return pd.DataFrame(
        {
            "time": times,
            "open": [1.0] * len(times),
            "high": highs,
            "low": [0.9998] * len(times),
            "close": [1.0001] * len(times),
            "tick_volume": [10] * len(times),
        }
    )


def _intent(*, with_economics: bool = False) -> TradeIntent:
    economics = (
        EntryEconomicsConstraints(
            minimum_risk_distance=0.0004,
            minimum_reward_distance=0.0006,
            reference_cost_distance=0.0001,
            minimum_cost_adjusted_reward_risk=1.5,
            maximum_spread_points=4.0,
            maximum_all_in_cost_distance=0.0001,
            required_entry_delay_seconds=60.0,
        )
        if with_economics
        else None
    )
    return TradeIntent(
        direction=TradeDirection.BUY,
        stop_loss=0.9995,
        take_profit=1.0010,
        maximum_holding_duration=timedelta(minutes=2),
        maximum_candle_gap=timedelta(minutes=1),
        entry_economics=economics,
    )


def test_time_exit_occurs_at_declared_deadline() -> None:
    frame = _candles(pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"))

    result = _backtester().run(frame, lambda history: _intent() if len(history) == 1 else None)

    trade = result.trades[0]
    assert trade.entry_time == frame["time"].iloc[1].to_pydatetime()
    assert trade.exit_time == frame["time"].iloc[3].to_pydatetime()
    assert trade.holding_duration == timedelta(minutes=2)
    assert trade.exit_reason == "time_exit"


def test_target_precedes_time_exit_on_deadline_candle() -> None:
    frame = _candles(
        pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"),
        deadline_hits_target=True,
    )

    result = _backtester().run(frame, lambda history: _intent() if len(history) == 1 else None)

    assert result.trades[0].exit_reason == "take_profit"


def test_actual_entry_economics_accept_exact_frozen_boundaries() -> None:
    frame = _candles(pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"))

    result = _backtester().run(
        frame,
        lambda history: _intent(with_economics=True) if len(history) == 1 else None,
    )

    assert result.accepted_trade_count == 1
    assert result.emitted_signal_count == 1
    assert result.rejected_intents == ()


def test_actual_entry_gap_rejects_reward_and_adjusted_ratio() -> None:
    frame = _candles(pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"))
    frame.loc[1, ["open", "high", "low", "close"]] = [1.0005, 1.0006, 1.0004, 1.0005]

    result = _backtester().run(
        frame,
        lambda history: _intent(with_economics=True) if len(history) == 1 else None,
    )

    assert result.accepted_trade_count == 0
    assert result.emitted_signal_count == 1
    assert "actual-entry reward distance" in result.rejected_intents[0]
    assert "cost-adjusted reward/risk" in result.rejected_intents[0]


def test_non_exact_next_m1_is_rejected_before_entry() -> None:
    times = pd.DatetimeIndex(
        ["2026-01-05 12:00Z", "2026-01-05 12:02Z", "2026-01-05 12:03Z"]
    )
    frame = _candles(times)

    result = _backtester().run(
        frame,
        lambda history: _intent(with_economics=True) if len(history) == 1 else None,
    )

    assert result.trade_count == 0
    assert "required next candle" in result.rejected_intents[0]


def test_open_trade_candle_gap_fails_loudly() -> None:
    times = pd.DatetimeIndex(
        ["2026-01-05 12:00Z", "2026-01-05 12:01Z", "2026-01-05 12:03Z"]
    )
    frame = _candles(times)

    with pytest.raises(ValueError, match="open position encountered a candle gap"):
        _backtester().run(frame, lambda history: _intent() if len(history) == 1 else None)

def test_entry_relative_target_is_resolved_from_actual_fill() -> None:
    frame = _candles(pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"))
    frame.loc[1, ["open", "high", "low", "close"]] = [1.0002, 1.0003, 1.0000, 1.0002]
    frame.loc[2, "high"] = 1.0017
    intent = TradeIntent(
        direction=TradeDirection.BUY,
        stop_loss=0.9995,
        take_profit=1.0010,
        target_reward_risk_multiple=2.0,
    )

    result = _backtester().run(frame, lambda history: intent if len(history) == 1 else None)

    trade = result.trades[0]
    assert trade.reference_entry_price == pytest.approx(1.0002)
    assert trade.target_price == pytest.approx(1.0016)
    assert trade.exit_reason == "take_profit"


def test_entry_relative_target_rejects_fill_beyond_stop() -> None:
    frame = _candles(pd.date_range("2026-01-05 12:00", periods=3, freq="min", tz="UTC"))
    frame.loc[1, ["open", "high", "low", "close"]] = [0.9994, 0.9996, 0.9993, 0.9994]
    intent = TradeIntent(
        direction=TradeDirection.BUY,
        stop_loss=0.9995,
        take_profit=1.0010,
        target_reward_risk_multiple=2.0,
    )

    result = _backtester().run(frame, lambda history: intent if len(history) == 1 else None)

    assert result.trade_count == 0
    assert "invalid entry-relative target" in result.rejected_intents[0]