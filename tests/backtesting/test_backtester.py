from datetime import timedelta

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, TradeIntent
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


def candles(*, both_hit: bool = False) -> pd.DataFrame:
    second_low = 0.998 if both_hit else 0.999
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"),
            "open": [1.0, 1.0, 1.002, 1.002],
            "high": [1.001, 1.003, 1.003, 1.003],
            "low": [0.999, second_low, 1.001, 1.001],
            "close": [1.0, 1.002, 1.002, 1.002],
            "tick_volume": [10, 10, 10, 10],
        }
    )


def symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(symbol="EURUSD", point=0.0001, tick_size=0.0001, tick_value=1.0, volume_min=0.01, volume_max=10, volume_step=0.01)


def backtester(**config_changes: float) -> CandleBacktester:
    config = BacktestConfig(initial_balance=10_000, **config_changes)
    limits = RiskLimits(max_lot_size=1, max_exposure_lots=1, min_reward_risk_ratio=1)
    return CandleBacktester(config, RiskEngine(limits), symbol())


def buy_once(history: pd.DataFrame) -> TradeIntent | None:
    if len(history) == 1:
        return TradeIntent(direction=TradeDirection.BUY, stop_loss=0.998, take_profit=1.002)
    return None


def test_enters_on_next_candle_and_exits_at_take_profit() -> None:
    result = backtester().run(candles(), buy_once)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == candles()["time"].iloc[1].to_pydatetime()
    assert trade.entry_price == 1.0
    assert trade.exit_reason == "take_profit"
    assert trade.net_pnl == pytest.approx(20.0)
    assert result.net_profit == pytest.approx(20.0)
    assert result.win_rate == 1.0
    assert result.profit_factor == float("inf")


def test_uses_conservative_stop_when_both_exit_prices_are_reached() -> None:
    result = backtester().run(candles(both_hit=True), buy_once)

    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].net_pnl == pytest.approx(-20.0)
    assert result.max_drawdown == pytest.approx(20.0)


def test_models_entry_friction_and_commission() -> None:
    def higher_target(history: pd.DataFrame) -> TradeIntent | None:
        if len(history) == 1:
            return TradeIntent(direction=TradeDirection.BUY, stop_loss=0.998, take_profit=1.003)
        return None

    result = backtester(spread_points=1, slippage_points=1, commission_per_lot_per_side=2).run(candles(), higher_target)

    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(1.0002)
    assert trade.symbol == "EURUSD"
    assert trade.stop_price == pytest.approx(0.998)
    assert trade.target_price == pytest.approx(1.003)
    assert trade.gross_pnl == pytest.approx(30.0)
    assert trade.spread_cost == pytest.approx(1.0)
    assert trade.slippage_cost == pytest.approx(1.0)
    assert trade.commission == pytest.approx(4.0)
    assert trade.total_transaction_cost == pytest.approx(6.0)
    assert trade.net_pnl == pytest.approx(24.0)
    assert trade.gross_pnl - trade.spread_cost - trade.slippage_cost - trade.commission == pytest.approx(trade.net_pnl)
    assert trade.holding_duration == timedelta(0)
    assert trade.mae == pytest.approx(-10.0)
    assert trade.mfe == pytest.approx(30.0)
    assert result.gross_pnl == pytest.approx(30.0)
    assert result.total_transaction_cost == pytest.approx(6.0)


def test_strategy_never_receives_future_candles() -> None:
    observed_lengths: list[int] = []

    def observe(history: pd.DataFrame) -> None:
        observed_lengths.append(len(history))
        assert history["time"].iloc[-1] == candles()["time"].iloc[len(history) - 1]
        return None

    result = backtester().run(candles(), observe)

    assert not result.trades
    assert observed_lengths == [1, 2, 3]


def test_rejected_risk_intent_is_recorded() -> None:
    def invalid_reward(history: pd.DataFrame) -> TradeIntent | None:
        if len(history) == 1:
            return TradeIntent(direction=TradeDirection.BUY, stop_loss=0.998, take_profit=1.001)
        return None

    result = backtester().run(candles(), invalid_reward)

    assert not result.trades
    assert "reward/risk" in result.rejected_intents[0]



def test_sell_trade_has_symmetric_cost_decomposition() -> None:
    sell_candles = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz="UTC"),
            "open": [1.0, 1.0, 0.996, 0.996],
            "high": [1.001, 1.0005, 0.997, 0.997],
            "low": [0.999, 0.9958, 0.995, 0.995],
            "close": [1.0, 0.996, 0.996, 0.996],
            "tick_volume": [10, 10, 10, 10],
        }
    )

    def sell_once(history: pd.DataFrame) -> TradeIntent | None:
        if len(history) == 1:
            return TradeIntent(
                direction=TradeDirection.SELL,
                stop_loss=1.0025,
                take_profit=0.996,
            )
        return None

    trade = backtester(
        spread_points=1,
        slippage_points=1,
        commission_per_lot_per_side=2,
    ).run(sell_candles, sell_once).trades[0]

    assert trade.entry_price == pytest.approx(0.9999)
    assert trade.exit_price == pytest.approx(0.996)
    assert trade.gross_pnl == pytest.approx(41.0)
    assert trade.spread_cost == pytest.approx(1.0)
    assert trade.slippage_cost == pytest.approx(1.0)
    assert trade.commission == pytest.approx(4.0)
    assert trade.net_pnl == pytest.approx(35.0)
    assert trade.gross_pnl - trade.total_transaction_cost == pytest.approx(
        trade.net_pnl
    )
    assert trade.mae == pytest.approx(-5.0)
    assert trade.mfe == pytest.approx(42.0)


def test_optional_evaluation_schedule_skips_history_allocation() -> None:
    class ScheduledNoop:
        required_history_bars = 1

        def __init__(self) -> None:
            self.observed: list[pd.Timestamp] = []

        def is_evaluation_time(self, timestamp: object) -> bool:
            return getattr(timestamp, "minute") == 1

        def __call__(self, history: pd.DataFrame) -> None:
            self.observed.append(history["time"].iloc[-1])
            return None

    strategy = ScheduledNoop()
    result = backtester().run(candles(), strategy)

    assert not result.trades
    assert strategy.observed == [candles()["time"].iloc[1]]