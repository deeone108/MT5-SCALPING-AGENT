import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mt5_scalping_agent.backtesting import BacktestTrade
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.research.continuous_evaluation import SplitIsolationError
from mt5_scalping_agent.research.registry import (
    EconomicPromotionGate,
    load_research_registry,
)
from mt5_scalping_agent.research.strategy16_evaluation import (
    BlockBootstrapSettings,
    Strategy16GateMetrics,
    block_bootstrap_report,
    strategy16_gate_report,
)
from mt5_scalping_agent.risk import SymbolRiskSpec


SYMBOL = SymbolRiskSpec(
    symbol="EURUSD",
    point=0.00001,
    tick_size=0.00001,
    tick_value=1.0,
    volume_min=0.01,
    volume_max=100.0,
    volume_step=0.01,
)


def _trade(entry: datetime, gross_pips: float, net_pips: float) -> BacktestTrade:
    return BacktestTrade(
        direction=TradeDirection.BUY,
        entry_time=entry,
        exit_time=entry + timedelta(minutes=30),
        entry_price=1.1000,
        exit_price=1.1010,
        volume_lots=1.0,
        gross_pnl=gross_pips * 10.0,
        net_pnl=net_pips * 10.0,
        exit_reason="fixture",
        symbol="EURUSD",
        spread_cost=(gross_pips - net_pips) * 10.0,
    )


def _gate() -> EconomicPromotionGate:
    registry = load_research_registry(
        Path("config/research_registry.json"),
        validate_evidence=False,
    )
    result = next(
        gate
        for gate in registry.promotion_gates
        if gate.gate_id == "strategy_16_event_economic_gate_v1"
    )
    assert isinstance(result, EconomicPromotionGate)
    return result


def _bootstrap_fixture(lower_gross: float = 1.6, lower_net: float = 0.1) -> dict:
    rows = {
        unit: {
            "gross_expectancy_pips": {"lower": lower_gross},
            "net_expectancy_pips": {"lower": lower_net},
            "implied_effective_sample_size": 1_500.0,
            "required_effective_sample_size": 1_000,
            "effective_sample_requirement_met": True,
        }
        for unit in ("day", "week")
    }
    return {"by_block_unit": rows}


def _passing_metrics() -> Strategy16GateMetrics:
    return Strategy16GateMetrics(
        base_emitted=300,
        base_accepted=300,
        base_rejected=0,
        stress_emitted=300,
        stress_accepted=300,
        stress_rejected=0,
        gross_expectancy_pips=3.2,
        base_net_expectancy_pips=2.1,
        stress_net_expectancy_pips=1.1,
        base_profit_factor=1.4,
        stress_profit_factor=1.2,
        median_mfe_pips=9.0,
        mfe_exceedance_ratio=0.7,
        median_adverse_mae_pips=5.0,
        base_cost_pips=1.0,
        stress_cost_pips=1.9,
        base_annual_trades=(60, 60, 60, 60, 60),
        stress_annual_trades=(60, 60, 60, 60, 60),
        base_max_entries_day=1,
        stress_max_entries_day=1,
        median_holding_minutes=30.0,
        maximum_holding_minutes=80.0,
        overnight_trades=0,
        minimum_stop_pips=5.0,
        minimum_reward_pips=10.0,
        minimum_stress_cost_adjusted_rr=1.3,
        stress_positive_years=4,
        stress_year_count=5,
        stress_positive_active_months=33,
        stress_active_months=60,
        stress_strongest_year_contribution=0.30,
        stress_top_decile_contribution=0.40,
        base_block_bootstrap=_bootstrap_fixture(),
        stress_block_bootstrap=_bootstrap_fixture(),
        downside_tail_reported=True,
        neighborhood_passed=True,
        risk_sized_max_drawdown_percent=9.5,
    )


def test_block_bootstrap_is_deterministic_and_preserves_calendar_clusters() -> None:
    entries = (
        datetime(2023, 1, 2, 13, tzinfo=UTC),
        datetime(2023, 1, 2, 14, tzinfo=UTC),
        datetime(2023, 1, 3, 13, tzinfo=UTC),
        datetime(2023, 1, 9, 13, tzinfo=UTC),
    )
    trades = tuple(
        _trade(entry, gross_pips=value + 1.0, net_pips=value)
        for entry, value in zip(entries, (2.0, -1.0, 3.0, -2.0), strict=True)
    )
    settings = BlockBootstrapSettings(random_seed=7, bootstrap_samples=200)

    first = block_bootstrap_report(
        trades,
        symbol=SYMBOL,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 2, 1, tzinfo=UTC),
        settings=settings,
    )
    second = block_bootstrap_report(
        trades,
        symbol=SYMBOL,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 2, 1, tzinfo=UTC),
        settings=settings,
    )

    assert first == second
    assert first["by_block_unit"]["day"]["active_block_count"] == 3
    assert first["by_block_unit"]["week"]["active_block_count"] == 2
    assert first["sample"]["trade_count"] == 4
    assert first["methodology"]["within_block_order_preserved"] is True
    json.dumps(first, allow_nan=False)


def test_block_bootstrap_rejects_post_selection_data() -> None:
    with pytest.raises(SplitIsolationError):
        block_bootstrap_report(
            (_trade(datetime(2024, 1, 1, tzinfo=UTC), 2.0, 1.0),),
            symbol=SYMBOL,
        )


def test_gate_metrics_enforce_emitted_accepted_rejected_identity() -> None:
    with pytest.raises(ValueError, match="base emitted"):
        replace(_passing_metrics(), base_emitted=1_501)


def test_gate_report_passes_development_but_keeps_tick_replay_separate() -> None:
    report = strategy16_gate_report(_passing_metrics(), _gate())

    assert report["development_decision"] == "PASS"
    assert report["failed_gate_ids"] == []
    assert report["pre_demo_gate"]["status"] == "NOT_EVALUATED"
    assert report["demo_eligible"] is False


def test_primary_failure_skips_robustness_and_downstream_work() -> None:
    report = strategy16_gate_report(
        replace(_passing_metrics(), gross_expectancy_pips=0.5),
        _gate(),
    )

    assert report["development_decision"] == "FAIL"
    assert "gross_expectancy" in report["failed_gate_ids"]
    statuses = {
        row["gate_id"]: row["status"]
        for row in report["development_gates"]
    }
    assert statuses["gross_block_bootstrap"] == "NOT_EVALUATED"
    assert statuses["strongest_year_concentration"] == "NOT_EVALUATED"
    assert statuses["parameter_neighborhood"] == "NOT_EVALUATED"



def test_missing_conditional_downstream_results_are_not_failures() -> None:
    metrics = replace(
        _passing_metrics(),
        neighborhood_passed=None,
        risk_sized_max_drawdown_percent=None,
    )
    report = strategy16_gate_report(metrics, _gate())
    statuses = {
        row["gate_id"]: row["status"]
        for row in report["development_gates"]
    }

    assert report["development_decision"] == "INCOMPLETE"
    assert statuses["parameter_neighborhood"] == "NOT_EVALUATED"
    assert statuses["risk_sized_drawdown"] == "NOT_EVALUATED"