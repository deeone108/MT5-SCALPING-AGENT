import json
from datetime import UTC, datetime, timedelta

import pytest

from mt5_scalping_agent.backtesting import BacktestTrade
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.research.statistical_robustness import (
    StatisticalRobustnessSettings,
    statistical_robustness_report,
)


PERIOD_START = datetime(2022, 1, 1, tzinfo=UTC)
PERIOD_END = datetime(2023, 1, 1, tzinfo=UTC)


def completed_trade(
    entry: datetime,
    *,
    gross_pnl: float,
    net_pnl: float,
) -> BacktestTrade:
    cost = gross_pnl - net_pnl
    return BacktestTrade(
        direction=TradeDirection.BUY,
        entry_time=entry,
        exit_time=entry + timedelta(minutes=1),
        entry_price=1.1,
        exit_price=1.2,
        volume_lots=0.1,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        exit_reason="take_profit" if net_pnl > 0 else "stop_loss",
        symbol="EURUSD",
        spread_cost=cost / 2,
        commission=cost / 2,
    )


def settings(seed: int = 123) -> StatisticalRobustnessSettings:
    return StatisticalRobustnessSettings(
        random_seed=seed,
        bootstrap_samples=300,
        top_trade_fractions=(0.5, 1.0),
    )


def test_bootstrap_is_deterministic_and_records_accounting_identity() -> None:
    pnls = (10.0, -4.0, 6.0, -2.0, 8.0, -3.0)
    trades = tuple(
        completed_trade(
            PERIOD_START + timedelta(days=index),
            gross_pnl=net + 2.0,
            net_pnl=net,
        )
        for index, net in enumerate(pnls)
    )

    first = statistical_robustness_report(
        trades,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )
    second = statistical_robustness_report(
        trades,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )
    other_seed = statistical_robustness_report(
        trades,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(456),
    )

    assert first == second
    assert (
        first["bootstrap"]["net_expectancy_per_trade"]
        != other_seed["bootstrap"]["net_expectancy_per_trade"]
    )
    assert first["sample"]["gross_pnl"] == pytest.approx(sum(pnls) + 12)
    assert first["sample"]["total_transaction_cost"] == pytest.approx(12)
    assert first["sample"]["net_pnl"] == pytest.approx(sum(pnls))
    assert first["sample"]["accounting_identity_residual"] == pytest.approx(0)
    assert first["sample"]["accounting_identity_holds"] is True
    assert first["methodology"]["settings"]["random_seed"] == 123
    json.dumps(first, allow_nan=False)


def test_profit_factor_distribution_counts_infinite_and_undefined_samples() -> None:
    all_winners = tuple(
        completed_trade(
            PERIOD_START + timedelta(days=index), gross_pnl=net + 1, net_pnl=net
        )
        for index, net in enumerate((2.0, 3.0, 5.0))
    )
    winners_report = statistical_robustness_report(
        all_winners,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )
    winner_pf = winners_report["bootstrap"]["profit_factor"]

    assert winner_pf["point_estimate"] == "infinity"
    assert winner_pf["finite_sample_count"] == 0
    assert winner_pf["infinite_sample_count"] == 300
    assert winner_pf["undefined_sample_count"] == 0

    flat = (
        completed_trade(PERIOD_START, gross_pnl=0.0, net_pnl=0.0),
    )
    flat_report = statistical_robustness_report(
        flat,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )
    flat_pf = flat_report["bootstrap"]["profit_factor"]
    assert flat_pf["point_estimate"] is None
    assert flat_pf["undefined_sample_count"] == 300


def test_empty_sample_is_json_safe_and_preserves_empty_calendar_periods() -> None:
    report = statistical_robustness_report(
        (),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )

    assert report["sample"]["trade_count"] == 0
    assert report["bootstrap"]["net_expectancy_per_trade"]["lower"] is None
    assert report["bootstrap"]["maximum_drawdown"]["sample_count"] == 0
    assert report["consistency"]["yearly"]["period_count"] == 1
    assert report["consistency"]["monthly"]["period_count"] == 12
    assert report["consistency"]["monthly"]["active_period_count"] == 0
    assert report["concentration"]["strongest_month"]["net"]["contribution_fraction"] is None
    assert report["downside_tail"]["expected_shortfall"] is None
    json.dumps(report, allow_nan=False)


def test_consistency_concentration_drawdown_and_downside_are_exact() -> None:
    trades = (
        completed_trade(
            datetime(2022, 1, 2, tzinfo=UTC), gross_pnl=12, net_pnl=10
        ),
        completed_trade(
            datetime(2022, 1, 3, tzinfo=UTC), gross_pnl=0, net_pnl=-2
        ),
        completed_trade(
            datetime(2022, 2, 2, tzinfo=UTC), gross_pnl=6, net_pnl=4
        ),
        completed_trade(
            datetime(2022, 12, 2, tzinfo=UTC), gross_pnl=1, net_pnl=-1
        ),
    )
    report = statistical_robustness_report(
        trades,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )

    monthly = report["consistency"]["monthly"]
    assert monthly["period_count"] == 12
    assert monthly["active_period_count"] == 3
    assert monthly["positive_period_count"] == 2
    assert monthly["negative_period_count"] == 1
    assert monthly["positive_period_fraction"] == pytest.approx(2 / 12)
    assert monthly["positive_active_period_fraction"] == pytest.approx(2 / 3)
    assert monthly["strongest_period"]["period"] == "2022-01"
    assert monthly["strongest_period"]["net_pnl"] == pytest.approx(8)
    assert monthly["weakest_period"]["period"] == "2022-12"

    concentration = report["concentration"]
    gross_top_half = concentration["gross_by_top_trades"][0]
    net_top_half = concentration["net_by_top_trades"][0]
    assert gross_top_half["contribution_fraction"] == pytest.approx(18 / 19)
    assert net_top_half["contribution_fraction"] == pytest.approx(1.0)
    assert concentration["strongest_month"]["gross"]["contribution_fraction"] == pytest.approx(12 / 19)
    assert concentration["strongest_month"]["net"]["contribution_fraction"] == pytest.approx(8 / 12)

    assert report["bootstrap"]["maximum_drawdown"]["point_estimate"] == pytest.approx(2)
    downside = report["downside_tail"]
    assert downside["worst_trade_net_pnl"] == pytest.approx(-2)
    assert downside["loss_trade_count"] == 2
    assert downside["loss_trade_fraction"] == pytest.approx(0.5)
    assert downside["maximum_consecutive_losses"] == 1


def test_trade_outside_statistical_period_is_rejected() -> None:
    outside = completed_trade(
        PERIOD_END, gross_pnl=2, net_pnl=1
    )

    with pytest.raises(ValueError, match="outside"):
        statistical_robustness_report(
            (outside,),
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            settings=settings(),
        )


def test_empty_month_cannot_outrank_an_active_losing_month() -> None:
    trades = (
        completed_trade(
            datetime(2022, 1, 2, tzinfo=UTC), gross_pnl=-2, net_pnl=-3
        ),
        completed_trade(
            datetime(2022, 2, 2, tzinfo=UTC), gross_pnl=0, net_pnl=-1
        ),
    )

    report = statistical_robustness_report(
        trades,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        settings=settings(),
    )

    monthly = report["consistency"]["monthly"]
    assert monthly["strongest_period"]["period"] == "2022-02"
    assert monthly["weakest_period"]["period"] == "2022-01"
    strongest_net = report["concentration"]["strongest_month"]["net"]
    assert strongest_net["period"] == "2022-02"
    assert strongest_net["period_pnl"] == pytest.approx(-1)
    assert strongest_net["contribution_fraction"] is None

def test_invalid_seed_and_nonfinite_economics_are_rejected() -> None:
    with pytest.raises(ValueError, match="random_seed"):
        StatisticalRobustnessSettings(random_seed=True)

    nonfinite = BacktestTrade(
        direction=TradeDirection.BUY,
        entry_time=PERIOD_START,
        exit_time=PERIOD_START + timedelta(minutes=1),
        entry_price=1.1,
        exit_price=1.2,
        volume_lots=0.1,
        gross_pnl=float("inf"),
        net_pnl=float("inf"),
        exit_reason="take_profit",
    )
    with pytest.raises(ValueError, match="finite"):
        statistical_robustness_report(
            (nonfinite,),
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            settings=settings(),
        )