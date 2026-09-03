from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, TradeIntent
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


def _symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.0001,
        tick_size=0.0001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=10,
        volume_step=0.01,
    )


def _backtester(limits: RiskLimits, **config: float) -> CandleBacktester:
    return CandleBacktester(
        BacktestConfig(initial_balance=10_000, **config),
        RiskEngine(limits),
        _symbol(),
    )


def _loss_candles(times: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": times,
            "open": [1.0] * len(times),
            "high": [1.0005] * len(times),
            "low": [0.9985] * len(times),
            "close": [1.0] * len(times),
            "tick_volume": [10] * len(times),
        }
    )


def _always_buy(history: pd.DataFrame) -> TradeIntent:
    return TradeIntent(
        direction=TradeDirection.BUY,
        stop_loss=0.999,
        take_profit=1.002,
    )


def test_backtester_propagates_consecutive_losses_and_resets_next_utc_day() -> None:
    times = pd.DatetimeIndex(
        [
            *pd.date_range("2026-01-05 12:00", periods=6, freq="min", tz=UTC),
            *pd.date_range("2026-01-06 12:00", periods=4, freq="min", tz=UTC),
        ]
    )
    limits = RiskLimits(
        min_reward_risk_ratio=1,
        max_daily_loss_percent=100,
        max_weekly_loss_percent=100,
        max_market_data_age_seconds=300,
    )

    result = _backtester(limits).run(_loss_candles(times), _always_buy)

    assert len(result.trades) == 6
    assert [trade.entry_time.date() for trade in result.trades].count(datetime(2026, 1, 5).date()) == 3
    assert [trade.entry_time.date() for trade in result.trades].count(datetime(2026, 1, 6).date()) == 3
    assert any("consecutive losses" in reason for reason in result.rejected_intents)
    assert any("stale" in reason for reason in result.rejected_intents)
    assert result.final_risk_state is not None
    assert result.final_risk_state.consecutive_losses == 3
    assert result.final_risk_state.daily_realized_pnl == pytest.approx(-30)
    assert result.final_risk_state.weekly_realized_pnl == pytest.approx(-60)


def test_backtester_enforces_hourly_trade_rate_from_tracked_entries() -> None:
    limits = RiskLimits(
        min_reward_risk_ratio=1,
        max_consecutive_losses=100,
        max_trades_per_hour=2,
        max_trades_per_day=100,
        max_daily_loss_percent=100,
        max_weekly_loss_percent=100,
    )
    candles = _loss_candles(pd.date_range("2026-01-05 12:00", periods=6, freq="min", tz=UTC))

    result = _backtester(limits).run(candles, _always_buy)

    assert len(result.trades) == 2
    assert any("trades per hour" in reason for reason in result.rejected_intents)
    assert result.final_risk_state is not None
    assert result.final_risk_state.trades_current_hour == 2
    assert result.final_risk_state.trades_current_day == 2


def test_backtester_enforces_daily_trade_rate_across_hours() -> None:
    limits = RiskLimits(
        min_reward_risk_ratio=1,
        max_consecutive_losses=100,
        max_trades_per_hour=10,
        max_trades_per_day=2,
        max_daily_loss_percent=100,
        max_weekly_loss_percent=100,
        max_market_data_age_seconds=4_000,
    )
    times = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-05 12:00", tz=UTC),
            pd.Timestamp("2026-01-05 12:01", tz=UTC),
            pd.Timestamp("2026-01-05 13:00", tz=UTC),
            pd.Timestamp("2026-01-05 14:00", tz=UTC),
        ]
    )

    result = _backtester(limits).run(_loss_candles(times), _always_buy)

    assert len(result.trades) == 2
    assert any("trades per day" in reason for reason in result.rejected_intents)


@pytest.mark.parametrize(
    "limits",
    [
        RiskLimits(
            min_reward_risk_ratio=1,
            max_consecutive_losses=100,
            max_daily_loss_percent=0.1,
            max_weekly_loss_percent=100,
        ),
        RiskLimits(
            min_reward_risk_ratio=1,
            max_consecutive_losses=100,
            max_daily_loss_percent=100,
            max_weekly_loss_percent=0.1,
        ),
    ],
)
def test_backtester_propagates_realized_loss_period_gates(limits: RiskLimits) -> None:
    candles = _loss_candles(pd.date_range("2026-01-05 12:00", periods=5, freq="min", tz=UTC))

    result = _backtester(limits).run(candles, _always_buy)

    assert len(result.trades) == 1
    assert any("loss has been reached" in reason for reason in result.rejected_intents)


def test_backtester_rejects_pending_signal_after_stale_market_gap() -> None:
    times = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-05 12:00", tz=UTC),
            pd.Timestamp("2026-01-05 12:10", tz=UTC),
            pd.Timestamp("2026-01-05 12:11", tz=UTC),
        ]
    )

    class BuyOnce:
        emitted = False

        def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
            if self.emitted:
                return None
            self.emitted = True
            return _always_buy(history)

    result = _backtester(RiskLimits(min_reward_risk_ratio=1)).run(
        _loss_candles(times), BuyOnce()
    )

    assert not result.trades
    assert result.rejected_intents == ("market data is stale",)


def test_backtester_spread_gate_uses_configured_simulated_spread() -> None:
    candles = _loss_candles(pd.date_range("2026-01-05 12:00", periods=3, freq="min", tz=UTC))

    result = _backtester(RiskLimits(min_reward_risk_ratio=1), spread_points=4).run(
        candles, _always_buy
    )

    assert not result.trades
    assert all("spread" in reason for reason in result.rejected_intents)


def test_equity_curve_and_drawdown_use_candle_close_mark_to_market_equity() -> None:
    candles = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05 12:00", periods=4, freq="min", tz=UTC),
            "open": [1.0, 1.0, 1.0, 1.0],
            "high": [1.001, 1.005, 1.011, 1.001],
            "low": [0.999, 0.995, 0.999, 0.989],
            "close": [1.0, 1.0, 1.01, 0.99],
            "tick_volume": [10, 10, 10, 10],
        }
    )

    def wide_trade(history: pd.DataFrame) -> TradeIntent | None:
        if len(history) == 1:
            return TradeIntent(
                direction=TradeDirection.BUY,
                stop_loss=0.98,
                take_profit=1.04,
            )
        return None

    result = _backtester(RiskLimits(min_reward_risk_ratio=1)).run(candles, wide_trade)

    assert result.equity_curve.loc[2, "equity"] == pytest.approx(10_025)
    assert result.equity_curve.loc[3, "equity"] == pytest.approx(9_975)
    assert result.equity_curve.loc[3, "peak_equity"] == pytest.approx(10_025)
    assert result.max_drawdown == pytest.approx(50)
    assert result.final_risk_state is not None
    assert result.final_risk_state.peak_equity == pytest.approx(10_025)
    assert result.final_risk_state.open_position_count == 0
    assert result.final_risk_state.current_exposure_lots == 0