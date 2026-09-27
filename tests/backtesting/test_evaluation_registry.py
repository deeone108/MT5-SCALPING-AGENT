from __future__ import annotations

from datetime import UTC, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.backtesting.evaluation import (
    EVALUATION_STRATEGIES,
    EvaluationBuildContext,
    XAU60BacktestStrategy,
    build_evaluation_strategy,
    evaluation_spec,
)
from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.domain import SignalProposal, TradeDirection


def _bars(periods: int, interval: timedelta = timedelta(minutes=1)) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05", periods=periods, freq=interval, tz=UTC),
            "open": [2000.0] * periods,
            "high": [2001.0] * periods,
            "low": [1999.0] * periods,
            "close": [2000.0] * periods,
            "tick_volume": [100.0] * periods,
        }
    )


def test_common_registry_contains_internal_trend_and_three_pinned_xau60_candidates():
    assert set(STRATEGIES).issubset(EVALUATION_STRATEGIES)
    assert set(EVALUATION_STRATEGIES) == set(STRATEGIES) | {
        "trend_scalper",
        "xau60_smc_scalper_v2_1",
        "xau60_trend_break_trauma_v2_1",
        "xau60_crt_tbs_v2_1",
    }
    assert len(EVALUATION_STRATEGIES) == 18


def test_registry_contract_is_machine_readable_and_parameters_are_frozen():
    smc = evaluation_spec("xau60_smc_scalper_v2_1")
    assert smc.evaluation_timeframe == "M15"
    assert smc.minimum_history_bars == 50
    assert smc.supported_symbols == ("XAUUSD",)
    assert smc.parameters_frozen is True
    assert "spread" in smc.required_columns

    trend = evaluation_spec("trend_scalper")
    assert trend.evaluation_timeframe == "M1"
    assert trend.context_timeframes == ("M5",)
    assert trend.minimum_history_bars == 34


def test_factory_returns_fresh_instances_for_independent_stateful_runs():
    context = EvaluationBuildContext(symbol="EURUSD")
    first = build_evaluation_strategy("london_range_breakout", context)
    second = build_evaluation_strategy("london_range_breakout", context)

    assert first is not second
    assert first.__class__ is second.__class__


def test_xau60_builder_fails_closed_for_wrong_symbol_before_strategy_runs():
    with pytest.raises(ValueError, match="does not support symbol EURUSD"):
        build_evaluation_strategy(
            "xau60_crt_tbs_v2_1",
            EvaluationBuildContext(symbol="EURUSD"),
        )


def test_trend_scalper_requires_explicit_multitimeframe_context():
    with pytest.raises(ValueError, match="positive instrument point"):
        build_evaluation_strategy(
            "trend_scalper",
            EvaluationBuildContext(symbol="EURUSD"),
        )

    with pytest.raises(ValueError, match="requires M5 context"):
        build_evaluation_strategy(
            "trend_scalper",
            EvaluationBuildContext(symbol="EURUSD", point=0.00001),
        )


class FakeXAUAdapter:
    minimum_bars = 2
    timeframe = "M5"
    interval = timedelta(minutes=5)
    required_columns = frozenset({"time", "open", "high", "low", "close", "volume"})

    def __init__(self) -> None:
        self.seen = None

    def propose(self, symbol, bars, observed_at):
        self.seen = SimpleNamespace(symbol=symbol, bars=bars.copy(), observed_at=observed_at)
        return SignalProposal(
            symbol=symbol,
            direction=TradeDirection.BUY,
            strategy="fake_xau",
            generated_at=observed_at,
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
            reasons=("synthetic",),
        )


def test_xau60_evaluation_adapter_preserves_causality_and_normalizes_volume_column():
    upstream = FakeXAUAdapter()
    strategy = XAU60BacktestStrategy(upstream)
    frame = _bars(2, timedelta(minutes=5))

    intent = strategy(frame)

    assert isinstance(intent, TradeIntent)
    assert intent.direction is TradeDirection.BUY
    assert upstream.seen.symbol == "XAUUSD"
    assert "volume" in upstream.seen.bars.columns
    assert upstream.seen.bars["volume"].tolist() == frame["tick_volume"].tolist()
    assert upstream.seen.observed_at == (
        frame["time"].iloc[-1].to_pydatetime() + timedelta(minutes=5)
    )


def test_xau60_evaluation_adapter_requires_source_declared_auxiliary_columns():
    upstream = FakeXAUAdapter()
    upstream.required_columns = upstream.required_columns | {"spread"}
    strategy = XAU60BacktestStrategy(upstream)
    frame = _bars(2, timedelta(minutes=5))

    with pytest.raises(ValueError, match="spread"):
        strategy(frame)


def test_unknown_strategy_fails_explicitly():
    with pytest.raises(KeyError, match="unknown evaluation strategy"):
        evaluation_spec("does_not_exist")
