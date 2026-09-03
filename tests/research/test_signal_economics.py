from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import BacktestResult, BacktestTrade
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.research.continuous_evaluation import SplitIsolationError
from mt5_scalping_agent.research.signal_economics import signal_economics_report
from mt5_scalping_agent.research.statistical_robustness import (
    StatisticalRobustnessSettings,
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


def _trade(
    entry: datetime,
    direction: TradeDirection,
    *,
    gross: float,
    mfe: float,
    mae: float,
    minutes: int,
    volume: float = 1.0,
) -> BacktestTrade:
    reference = 1.1000
    if direction is TradeDirection.BUY:
        entry_price = 1.10003
        exit_price = entry_price + gross / 100_000.0 - 0.00003
        stop, target = 1.0990, 1.1020
    else:
        entry_price = 1.09999
        exit_price = entry_price - gross / 100_000.0 + 0.00003
        stop, target = 1.1010, 1.0980
    return BacktestTrade(
        direction=direction,
        entry_time=entry,
        exit_time=entry + timedelta(minutes=minutes),
        entry_price=entry_price,
        exit_price=exit_price,
        volume_lots=volume,
        gross_pnl=gross,
        net_pnl=gross - 7.0 * volume,
        exit_reason="fixture",
        symbol="EURUSD",
        reference_entry_price=reference,
        stop_price=stop,
        target_price=target,
        spread_cost=2.0 * volume,
        slippage_cost=1.0 * volume,
        commission=4.0 * volume,
        mae=mae * volume,
        mfe=mfe * volume,
        spread_cost_per_point=1.0 * volume,
    )


def _candles(times: list[datetime]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.to_datetime(times, utc=True),
            "open": [1.1000] * len(times),
            "high": [1.1002] * len(times),
            "low": [1.0998] * len(times),
            "close": [1.1001] * len(times),
            "tick_volume": [10] * len(times),
        }
    )


def test_signal_report_normalizes_economics_excursions_and_plan_distances() -> None:
    first = datetime(2023, 1, 9, 13, 0, tzinfo=UTC)
    second = datetime(2023, 7, 3, 12, 0, tzinfo=UTC)
    trades = (
        _trade(
            first,
            TradeDirection.BUY,
            gross=10.0,
            mfe=8.0,
            mae=-4.0,
            minutes=5,
        ),
        _trade(
            second,
            TradeDirection.SELL,
            gross=-2.0,
            mfe=21.0,
            mae=-10.0,
            minutes=15,
        ),
    )
    frame = _candles([first, second])
    volatility = pd.DataFrame(
        {"time": frame["time"], "volatility_regime": ["high", "low"]}
    )
    report = signal_economics_report(
        BacktestResult(
            trades,
            ("spread exceeds configured maximum",),
            pd.DataFrame({"equity": [10_000, 10_003, 9_994]}),
        ),
        frame,
        strategy_name="new_york_reversal",
        fixed_volume_lots=1.0,
        initial_balance=10_000.0,
        symbol=SYMBOL,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 8, 1, tzinfo=UTC),
        precomputed_volatility=volatility,
        statistical_settings=StatisticalRobustnessSettings(
            random_seed=9, bootstrap_samples=20
        ),
    )

    assert report["signal_definition"]["signal_count"] == 2
    assert report["signal_definition"]["rejected_intent_count"] == 1
    complete = report["signal_economics"]["complete"]
    assert complete["gross"]["expectancy_usd_per_signal"] == pytest.approx(4.0)
    assert complete["gross"]["expectancy_pips_per_signal"] == pytest.approx(0.4)
    assert complete["costs"]["all_in_expectancy_usd_per_signal"] == pytest.approx(7.0)
    assert complete["costs"]["all_in_expectancy_pips_per_signal"] == pytest.approx(0.7)
    assert complete["net"]["total_usd"] == pytest.approx(-6.0)
    assert complete["mfe"]["distribution_usd"]["median"] == pytest.approx(14.5)
    assert complete["mfe"]["distribution_pips"]["median"] == pytest.approx(1.45)
    assert complete["mae"]["signed_distribution_usd"]["median"] == pytest.approx(-7.0)
    assert complete["mae"]["adverse_magnitude_distribution_pips"]["median"] == pytest.approx(0.7)
    multiples = complete["mfe_cost_multiples"]
    assert multiples["strictly_exceeds_1x_cost_percent"] == pytest.approx(100.0)
    assert multiples["strictly_exceeds_2x_cost_percent"] == pytest.approx(50.0)
    assert multiples["strictly_exceeds_3x_cost_percent"] == pytest.approx(0.0)
    planned = complete["planned_distances"]
    assert planned["stop_distance_pips"]["median"] == pytest.approx(10.0)
    assert planned["target_distance_pips"]["median"] == pytest.approx(20.0)
    assert planned["cost_to_stop_ratio"]["median"] == pytest.approx(0.07)
    assert planned["target_to_cost_ratio"]["median"] == pytest.approx(20.0 / 0.7)
    assert complete["holding_duration_minutes"]["median"] == pytest.approx(10.0)
    assert report["accounting_audit"]["gross_minus_cost_equals_net"] is True


def test_signal_report_partitions_are_complete_and_dst_aware() -> None:
    winter = datetime(2023, 1, 9, 13, 0, tzinfo=UTC)
    summer = datetime(2023, 7, 3, 12, 0, tzinfo=UTC)
    trades = (
        _trade(winter, TradeDirection.BUY, gross=10, mfe=8, mae=-4, minutes=5),
        _trade(summer, TradeDirection.SELL, gross=-2, mfe=21, mae=-10, minutes=15),
    )
    frame = _candles([winter, summer])
    volatility = pd.DataFrame(
        {"time": frame["time"], "volatility_regime": ["high", "low"]}
    )
    report = signal_economics_report(
        BacktestResult(trades, (), pd.DataFrame()),
        frame,
        strategy_name="new_york_bollinger_rsi_reversal",
        fixed_volume_lots=1.0,
        symbol=SYMBOL,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 8, 1, tzinfo=UTC),
        precomputed_volatility=volatility,
        statistical_settings=StatisticalRobustnessSettings(bootstrap_samples=20),
    )
    economics = report["signal_economics"]
    assert sum(row["signal_count"] for row in economics["by_year"]) == 2
    assert sum(row["signal_count"] for row in economics["by_month"]) == 2
    assert sum(row["signal_count"] for row in economics["by_direction"]) == 2
    assert sum(
        row["signal_count"] for row in economics["by_causal_volatility_regime"]
    ) == 2
    subsections = {
        row["group"]: row["signal_count"]
        for row in economics["by_new_york_local_subsection"]
    }
    assert subsections["08:00-09:00"] == 2
    assert report["trades"][0]["diagnostic_labels"]["new_york_session_subsection"] == "08:00-09:00"
    assert report["summaries"]["complete"]["gross_pnl"] == pytest.approx(8.0)
    assert report["statistical_robustness"]["sample"]["accounting_identity_holds"] is True


def test_signal_report_rejects_nonconstant_volume() -> None:
    entry = datetime(2023, 1, 9, 13, 0, tzinfo=UTC)
    result = BacktestResult(
        (_trade(entry, TradeDirection.BUY, gross=1, mfe=2, mae=-1, minutes=1, volume=0.5),),
        (),
        pd.DataFrame(),
    )
    with pytest.raises(ValueError, match="fixed_volume_lots"):
        signal_economics_report(
            result,
            _candles([entry]),
            strategy_name="new_york_reversal",
            fixed_volume_lots=1.0,
            symbol=SYMBOL,
            period_start=datetime(2023, 1, 1, tzinfo=UTC),
            period_end=datetime(2023, 2, 1, tzinfo=UTC),
        )


def test_signal_report_rejects_post_selection_data() -> None:
    leaked = datetime(2024, 1, 1, tzinfo=UTC)
    with pytest.raises(SplitIsolationError, match="outside"):
        signal_economics_report(
            BacktestResult((), (), pd.DataFrame()),
            _candles([leaked]),
            strategy_name="new_york_reversal",
            fixed_volume_lots=1.0,
            symbol=SYMBOL,
        )