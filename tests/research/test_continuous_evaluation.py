from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import BacktestResult, BacktestTrade
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.research.statistical_robustness import StatisticalRobustnessSettings
from mt5_scalping_agent.research.continuous_evaluation import (
    DEVELOPMENT_END,
    SplitIsolationError,
    VolatilityRegimeSettings,
    assert_development_period,
    causal_volatility_regimes,
    continuous_result_report,
)


def candles_at(times: list[datetime]) -> pd.DataFrame:
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


def trade(
    entry: datetime,
    direction: TradeDirection,
    *,
    gross_pnl: float,
    net_pnl: float,
) -> BacktestTrade:
    transaction_cost = gross_pnl - net_pnl
    return BacktestTrade(
        direction=direction,
        entry_time=entry,
        exit_time=entry + timedelta(minutes=1),
        entry_price=1.1000,
        exit_price=1.1001,
        volume_lots=0.1,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        exit_reason="take_profit" if net_pnl > 0 else "stop_loss",
        symbol="EURUSD",
        stop_price=1.0990,
        target_price=1.1020,
        spread_cost=transaction_cost / 2,
        slippage_cost=0.0,
        commission=transaction_cost / 2,
        mae=-4.0,
        mfe=12.0,
        spread_cost_per_point=1.0,
    )


def test_split_boundary_is_half_open_and_rejects_post_selection_dates() -> None:
    assert assert_development_period(
        datetime(2019, 1, 1, tzinfo=UTC), DEVELOPMENT_END
    )[1] == DEVELOPMENT_END

    with pytest.raises(SplitIsolationError, match="post-selection"):
        assert_development_period(
            datetime(2019, 1, 1, tzinfo=UTC),
            DEVELOPMENT_END + timedelta(minutes=1),
        )


def test_report_rejects_2024_candles_even_when_trades_are_development_only() -> None:
    frame = candles_at(
        [
            datetime(2023, 12, 31, 23, 59, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        ]
    )
    result = BacktestResult((), (), pd.DataFrame())

    with pytest.raises(SplitIsolationError, match="outside"):
        continuous_result_report(
            result,
            frame,
            initial_balance=10_000,
            symbol="EURUSD",
        )


def test_report_rejects_a_post_selection_trade() -> None:
    frame = candles_at([datetime(2023, 12, 31, 23, 58, tzinfo=UTC)])
    leaked = trade(
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        TradeDirection.BUY,
        gross_pnl=12,
        net_pnl=10,
    )

    with pytest.raises(SplitIsolationError, match="trade outside"):
        continuous_result_report(
            BacktestResult((leaked,), (), pd.DataFrame()),
            frame,
            initial_balance=10_000,
            symbol="EURUSD",
        )


def test_report_partitions_calendar_direction_dst_session_and_regime() -> None:
    january_entry = datetime(2023, 1, 9, 13, 0, tzinfo=UTC)
    july_entry = datetime(2023, 7, 3, 7, 30, tzinfo=UTC)
    frame = candles_at([january_entry, july_entry])
    trades = (
        trade(
            january_entry,
            TradeDirection.BUY,
            gross_pnl=12,
            net_pnl=10,
        ),
        trade(
            july_entry,
            TradeDirection.SELL,
            gross_pnl=-3,
            net_pnl=-5,
        ),
    )
    result = BacktestResult(
        trades,
        (),
        pd.DataFrame({"equity": [10_000, 10_010, 10_005]}),
    )
    volatility = pd.DataFrame(
        {
            "time": frame["time"],
            "volatility_regime": ["high", "low"],
        }
    )

    report = continuous_result_report(
        result,
        frame,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 8, 1, tzinfo=UTC),
        initial_balance=10_000,
        symbol="EURUSD",
        statistical_settings=StatisticalRobustnessSettings(
            random_seed=7, bootstrap_samples=50
        ),
        precomputed_volatility=volatility,
    )

    summaries = report["summaries"]
    assert summaries["complete"]["trade_count"] == 2
    assert summaries["complete"]["gross_pnl"] == pytest.approx(9)
    assert summaries["complete"]["total_transaction_cost"] == pytest.approx(4)
    assert summaries["complete"]["net_profit"] == pytest.approx(5)
    assert sum(row["trade_count"] for row in summaries["by_month"]) == 2
    assert sum(row["trade_count"] for row in summaries["by_quarter"]) == 2
    assert sum(row["trade_count"] for row in summaries["by_direction"]) == 2
    assert sum(row["trade_count"] for row in summaries["by_session"]) == 2
    assert sum(row["trade_count"] for row in summaries["by_volatility_regime"]) == 2
    sessions = {
        row["group"]: row["trade_count"] for row in summaries["by_session"]
    }
    assert sessions["new_york"] == 1
    assert sessions["london"] == 1
    months = {row["group"]: row["trade_count"] for row in summaries["by_month"]}
    assert months["2023-01"] == 1
    assert months["2023-02"] == 0
    assert months["2023-07"] == 1
    assert report["period"]["post_selection_data_used"] is False
    assert report["statistical_robustness"]["sample"]["net_pnl"] == pytest.approx(5)
    assert report["statistical_robustness"]["methodology"]["settings"]["random_seed"] == 7
    assert report["trades"][0]["diagnostic_labels"]["volatility_regime"] == "high"
    assert report["trades"][1]["diagnostic_labels"]["volatility_regime"] == "low"


def test_volatility_label_at_entry_does_not_use_that_candle_or_future_candles() -> None:
    start = datetime(2023, 1, 2, tzinfo=UTC)
    frame = candles_at([start + timedelta(minutes=index) for index in range(30)])
    settings = VolatilityRegimeSettings(
        atr_period_bars=2,
        baseline_window_bars=4,
        baseline_minimum_bars=2,
        low_ratio_maximum=0.75,
        high_ratio_minimum=1.50,
    )
    baseline = causal_volatility_regimes(frame, settings)
    changed = frame.copy()
    changed.loc[20:, "high"] = 1.2
    changed.loc[20:, "low"] = 1.0

    modified = causal_volatility_regimes(changed, settings)

    pd.testing.assert_series_equal(
        baseline.loc[:20, "volatility_ratio"],
        modified.loc[:20, "volatility_ratio"],
    )
    pd.testing.assert_series_equal(
        baseline.loc[:20, "volatility_regime"],
        modified.loc[:20, "volatility_regime"],
    )


def test_precomputed_volatility_must_align_with_candles() -> None:
    entry = datetime(2023, 1, 2, tzinfo=UTC)
    frame = candles_at([entry, entry + timedelta(minutes=1)])
    reversed_labels = pd.DataFrame(
        {
            "time": frame["time"].iloc[::-1].reset_index(drop=True),
            "volatility_regime": ["normal", "normal"],
        }
    )

    with pytest.raises(ValueError, match="align"):
        continuous_result_report(
            BacktestResult((), (), pd.DataFrame()),
            frame,
            period_start=entry,
            period_end=entry + timedelta(days=1),
            initial_balance=10_000,
            symbol="EURUSD",
            precomputed_volatility=reversed_labels,
        )
