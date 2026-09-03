from datetime import UTC, datetime, timedelta
import json

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import (
    BacktestResult,
    BacktestTrade,
    backtest_summary,
    trade_record,
)
from mt5_scalping_agent.domain import TradeDirection


def completed_trade(
    *,
    direction: TradeDirection,
    entry_time: datetime,
    duration_minutes: int,
    volume_lots: float,
    gross_pnl: float,
    spread_cost: float,
    slippage_cost: float,
    commission: float,
    net_pnl: float,
    mae: float,
    mfe: float,
    spread_cost_per_point: float,
) -> BacktestTrade:
    return BacktestTrade(
        direction=direction,
        entry_time=entry_time,
        exit_time=entry_time + timedelta(minutes=duration_minutes),
        entry_price=1.1,
        exit_price=1.2,
        volume_lots=volume_lots,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        exit_reason="take_profit" if net_pnl > 0 else "stop_loss",
        symbol="EURUSD",
        stop_price=1.09,
        target_price=1.12,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        commission=commission,
        mae=mae,
        mfe=mfe,
        spread_cost_per_point=spread_cost_per_point,
    )


def test_summary_reports_complete_trade_economics_and_legacy_net_profit() -> None:
    entry = datetime(2026, 1, 5, 12, tzinfo=UTC)
    winner = completed_trade(
        direction=TradeDirection.BUY,
        entry_time=entry,
        duration_minutes=2,
        volume_lots=0.1,
        gross_pnl=20.0,
        spread_cost=1.0,
        slippage_cost=1.0,
        commission=2.0,
        net_pnl=16.0,
        mae=-5.0,
        mfe=25.0,
        spread_cost_per_point=1.0,
    )
    loser = completed_trade(
        direction=TradeDirection.SELL,
        entry_time=entry + timedelta(hours=1),
        duration_minutes=4,
        volume_lots=0.2,
        gross_pnl=-6.0,
        spread_cost=1.0,
        slippage_cost=1.0,
        commission=2.0,
        net_pnl=-10.0,
        mae=-12.0,
        mfe=3.0,
        spread_cost_per_point=2.0,
    )
    result = BacktestResult(
        (winner, loser),
        (),
        pd.DataFrame({"equity": [100.0, 116.0, 106.0]}),
    )

    summary = backtest_summary(result)

    assert summary["symbol"] == "EURUSD"
    assert summary["trade_count"] == 2
    assert summary["total_lots"] == pytest.approx(0.3)
    assert summary["gross_pnl"] == pytest.approx(14.0)
    assert summary["total_spread_cost"] == pytest.approx(2.0)
    assert summary["total_slippage_cost"] == pytest.approx(2.0)
    assert summary["total_commission"] == pytest.approx(4.0)
    assert summary["total_transaction_cost"] == pytest.approx(8.0)
    assert summary["net_pnl"] == pytest.approx(6.0)
    assert summary["net_profit"] == pytest.approx(6.0)
    assert summary["gross_expectancy_per_trade"] == pytest.approx(7.0)
    assert summary["net_expectancy_per_trade"] == pytest.approx(3.0)
    assert summary["average_winner"] == pytest.approx(16.0)
    assert summary["average_loser"] == pytest.approx(-10.0)
    assert summary["win_rate"] == pytest.approx(0.5)
    assert summary["payoff_ratio"] == pytest.approx(1.6)
    assert summary["profit_factor"] == pytest.approx(1.6)
    assert summary["max_drawdown"] == pytest.approx(10.0)
    assert summary["average_holding_duration_seconds"] == pytest.approx(180.0)
    assert summary["average_mae"] == pytest.approx(-8.5)
    assert summary["average_mfe"] == pytest.approx(14.0)
    assert summary["break_even_transaction_cost_per_trade"] == pytest.approx(7.0)
    assert summary["break_even_spread_points"] == pytest.approx(8.0 / 3.0)
    json.dumps(summary, allow_nan=False)


def test_trade_record_serializes_duration_and_cost_identity() -> None:
    trade = completed_trade(
        direction=TradeDirection.BUY,
        entry_time=datetime(2026, 1, 5, 12, tzinfo=UTC),
        duration_minutes=3,
        volume_lots=0.1,
        gross_pnl=12.0,
        spread_cost=1.0,
        slippage_cost=0.5,
        commission=0.5,
        net_pnl=10.0,
        mae=-2.0,
        mfe=14.0,
        spread_cost_per_point=1.0,
    )

    record = trade_record(trade)

    assert record["holding_duration_seconds"] == 180.0
    assert record["gross_pnl"] - record["spread_cost"] - record["slippage_cost"] - record["commission"] == pytest.approx(record["net_pnl"])
    assert record["total_transaction_cost"] == pytest.approx(2.0)
    assert record["stop_price"] == pytest.approx(1.09)
    assert record["target_price"] == pytest.approx(1.12)


def test_trade_rejects_inconsistent_cost_accounting() -> None:
    entry = datetime(2026, 1, 5, 12, tzinfo=UTC)

    with pytest.raises(ValueError, match="gross PnL"):
        BacktestTrade(
            TradeDirection.BUY,
            entry,
            entry + timedelta(minutes=1),
            1.1,
            1.2,
            0.1,
            10.0,
            9.0,
            "take_profit",
            spread_cost=2.0,
        )


def test_empty_summary_has_zero_totals_and_no_expectancies() -> None:
    summary = backtest_summary(BacktestResult((), (), pd.DataFrame()), symbol="EURUSD")

    assert summary["trade_count"] == 0
    assert summary["gross_pnl"] == 0.0
    assert summary["total_transaction_cost"] == 0.0
    assert summary["net_profit"] == 0.0
    assert summary["gross_expectancy_per_trade"] is None
    assert summary["break_even_spread_points"] is None
    assert summary["rejected_intent_reason_counts"] == {}


def test_negative_gross_edge_has_no_nonnegative_break_even_cost() -> None:
    entry = datetime(2026, 1, 5, 12, tzinfo=UTC)
    trade = completed_trade(
        direction=TradeDirection.BUY,
        entry_time=entry,
        duration_minutes=1,
        volume_lots=0.1,
        gross_pnl=-1.0,
        spread_cost=1.0,
        slippage_cost=1.0,
        commission=1.0,
        net_pnl=-4.0,
        mae=-5.0,
        mfe=0.0,
        spread_cost_per_point=1.0,
    )
    result = BacktestResult((trade,), (), pd.DataFrame())

    assert result.break_even_transaction_cost_per_trade is None
    assert result.break_even_spread_points is None


def test_summary_counts_each_individual_rejection_reason() -> None:
    result = BacktestResult(
        (),
        (
            "spread exceeds configured maximum; maximum trades per day has been reached",
            "spread exceeds configured maximum",
        ),
        pd.DataFrame(),
    )

    summary = backtest_summary(result, symbol="EURUSD")

    assert summary["rejected_intent_count"] == 2
    assert summary["rejected_intent_reason_counts"] == {
        "maximum trades per day has been reached": 1,
        "spread exceeds configured maximum": 2,
    }