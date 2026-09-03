from datetime import UTC, datetime, timedelta

import pandas as pd

from mt5_scalping_agent.backtesting import BacktestResult, BacktestTrade
from mt5_scalping_agent.domain import TradeDirection
from scripts.run_experiments import _trade_diagnostics, candidate_configurations, parse_arguments


def test_candidate_configurations_are_named_and_interpretable() -> None:
    candidates = candidate_configurations()

    assert [candidate.name for candidate in candidates] == [
        "baseline",
        "london_morning",
        "strict_rsi",
        "tight_spread",
        "m5_trend_strength",
        "m1_volatility",
        "m1_pullback",
        "wider_target",
    ]
    assert candidates[0].strategy_config.session_end_utc.hour == 20
    assert candidates[1].strategy_config.session_end_utc.hour == 12
    assert candidates[2].strategy_config.buy_rsi_minimum == 55
    assert candidates[3].strategy_config.max_spread_points == 1.5
    assert candidates[4].strategy_config.min_m5_trend_strength == 0.15
    assert candidates[5].strategy_config.min_m1_atr_fraction == 0.000058
    assert candidates[6].strategy_config.require_m1_pullback is True
    assert candidates[7].strategy_config.take_profit_atr_multiple == 2.5


def test_parse_arguments_selects_existing_candidates() -> None:
    args = parse_arguments([
        "--start", "2025-01-05T00:00:00Z", "--end", "2025-01-06T00:00:00Z",
        "--experiments", "london_morning", "m1_pullback",
    ])

    assert args.experiments == ["london_morning", "m1_pullback"]


def test_trade_diagnostics_groups_completed_trades() -> None:
    entry = datetime(2025, 1, 6, 7, tzinfo=UTC)
    trades = (
        BacktestTrade(TradeDirection.BUY, entry, entry + timedelta(minutes=2), 1.1, 1.2, 0.1, 10.0, 10.0, "take_profit"),
        BacktestTrade(TradeDirection.SELL, entry + timedelta(hours=1), entry + timedelta(hours=1, minutes=4), 1.2, 1.3, 0.1, -5.0, -5.0, "stop_loss"),
    )

    diagnostics = _trade_diagnostics(BacktestResult(trades, (), pd.DataFrame()))

    assert diagnostics["average_holding_minutes"] == 3.0
    assert diagnostics["by_entry_hour_utc"][0]["group"] == "07"
    assert diagnostics["by_direction"][0]["trade_count"] == 1
    assert {item["group"] for item in diagnostics["by_exit_reason"]} == {"stop_loss", "take_profit"}
