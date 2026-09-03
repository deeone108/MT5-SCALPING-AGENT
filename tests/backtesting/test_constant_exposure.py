from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from mt5_scalping_agent.backtesting import (
    BacktestConfig,
    CandleBacktester,
    PositionSizingMode,
    TradeIntent,
)
from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.risk import (
    AccountRiskState,
    RiskEngine,
    RiskLimits,
    SymbolRiskSpec,
    TradePlan,
)


def _symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.0001,
        tick_size=0.0001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=10.0,
        volume_step=0.01,
    )


def _limits(**updates: object) -> RiskLimits:
    return RiskLimits(
        min_reward_risk_ratio=1.0,
        max_lot_size=1.0,
        max_exposure_lots=1.0,
        **updates,
    )


def _always_buy(_: pd.DataFrame) -> TradeIntent:
    return TradeIntent(
        direction=TradeDirection.BUY,
        stop_loss=0.999,
        take_profit=1.002,
    )


def _plan(**updates: object) -> TradePlan:
    values: dict[str, object] = {
        "symbol": "EURUSD",
        "direction": TradeDirection.BUY,
        "entry_price": 1.0,
        "stop_loss": 0.999,
        "take_profit": 1.002,
        "spread_points": 1.0,
    }
    values.update(updates)
    return TradePlan.model_validate(values)


def _account(**updates: object) -> AccountRiskState:
    values: dict[str, object] = {
        "equity": 10_000.0,
        "balance": 10_000.0,
        "peak_equity": 10_000.0,
    }
    values.update(updates)
    return AccountRiskState.model_validate(values)

def test_fixed_lot_configuration_is_explicit_and_manifest_serializable() -> None:
    config = BacktestConfig(
        initial_balance=10_000,
        position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
        fixed_volume_lots=1.0,
    )

    assert config.model_dump(mode="json")["position_sizing_mode"] == (
        "research_fixed_lot"
    )
    assert config.model_dump(mode="json")["fixed_volume_lots"] == 1.0

    with pytest.raises(ValidationError, match="fixed_volume_lots is required"):
        BacktestConfig(
            initial_balance=10_000,
            position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
        )
    with pytest.raises(ValidationError, match="only valid"):
        BacktestConfig(initial_balance=10_000, fixed_volume_lots=1.0)


def test_fixed_lot_mode_is_not_censored_by_equity_minimum_size_or_circuit_breakers() -> None:
    times = pd.DatetimeIndex(
        [
            *pd.date_range("2026-01-05 12:00", periods=3, freq="min", tz="UTC"),
            *pd.date_range("2026-01-06 12:00", periods=3, freq="min", tz="UTC"),
        ]
    )
    candles = pd.DataFrame(
        {
            "time": times,
            "open": [1.0] * len(times),
            "high": [1.0005] * len(times),
            "low": [0.9985] * len(times),
            "close": [1.0] * len(times),
            "tick_volume": [10] * len(times),
        }
    )
    limits = _limits(
        max_daily_loss_percent=0.01,
        max_weekly_loss_percent=0.01,
        max_drawdown_percent=0.01,
        max_consecutive_losses=1,
        max_trades_per_hour=1,
        max_trades_per_day=1,
    )
    normal = CandleBacktester(
        BacktestConfig(initial_balance=1.0),
        RiskEngine(limits),
        _symbol(),
    ).run(candles, _always_buy)
    fixed = CandleBacktester(
        BacktestConfig(
            initial_balance=1.0,
            position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
            fixed_volume_lots=1.0,
        ),
        RiskEngine(limits),
        _symbol(),
    ).run(candles, _always_buy)

    assert not normal.trades
    assert any("below the broker minimum" in reason for reason in normal.rejected_intents)
    assert len(fixed.trades) == 4
    assert {trade.volume_lots for trade in fixed.trades} == {1.0}
    assert fixed.final_risk_state is not None
    assert fixed.final_risk_state.balance == pytest.approx(-39.0)
    assert fixed.final_risk_state.daily_starting_equity == pytest.approx(-19.0)
    assert not any(
        marker in reason
        for reason in fixed.rejected_intents
        for marker in (
            "minimum volume",
            "depleted",
            "loss has been reached",
            "drawdown",
            "consecutive losses",
            "trades per",
        )
    )


@pytest.mark.parametrize(
    ("direction", "final_close"),
    [
        (TradeDirection.BUY, 1.001),
        (TradeDirection.SELL, 0.999),
    ],
)
def test_fixed_lot_buy_sell_economics_are_symmetric_and_accounting_balances(
    direction: TradeDirection,
    final_close: float,
) -> None:
    candles = pd.DataFrame(
        {
            "time": pd.date_range(
                "2026-01-05 12:00", periods=3, freq="min", tz="UTC"
            ),
            "open": [1.0, 1.0, 1.0],
            "high": [1.001, 1.001, 1.001],
            "low": [0.999, 0.999, 0.999],
            "close": [1.0, 1.0, final_close],
            "tick_volume": [10, 10, 10],
        }
    )

    def signal_once(history: pd.DataFrame) -> TradeIntent | None:
        if len(history) != 1:
            return None
        return TradeIntent(
            direction=direction,
            stop_loss=0.99 if direction is TradeDirection.BUY else 1.01,
            take_profit=1.02 if direction is TradeDirection.BUY else 0.98,
        )

    result = CandleBacktester(
        BacktestConfig(
            initial_balance=10_000,
            spread_points=2.0,
            slippage_points=1.0,
            commission_per_lot_per_side=2.0,
            position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
            fixed_volume_lots=1.0,
        ),
        RiskEngine(_limits()),
        _symbol(),
    ).run(candles, signal_once)

    assert result.trade_count == 1
    trade = result.trades[0]
    assert trade.volume_lots == 1.0
    assert trade.reference_entry_price == pytest.approx(1.0)
    assert trade.gross_pnl == pytest.approx(10.0)
    assert trade.spread_cost == pytest.approx(2.0)
    assert trade.slippage_cost == pytest.approx(1.0)
    assert trade.commission == pytest.approx(4.0)
    assert trade.total_transaction_cost == pytest.approx(7.0)
    assert trade.net_pnl == pytest.approx(3.0)
    assert trade.gross_pnl - trade.total_transaction_cost == pytest.approx(
        trade.net_pnl
    )
    assert trade.mae == pytest.approx(-10.0)
    assert trade.mfe == pytest.approx(10.0)

def test_fixed_lot_mode_preserves_nonportfolio_and_broker_rejection_gates() -> None:
    def reasons(
        *,
        plan: TradePlan | None = None,
        account: AccountRiskState | None = None,
        volume: float = 1.0,
        limits: RiskLimits | None = None,
    ) -> tuple[str, ...]:
        return RiskEngine(limits or _limits()).assess_research_fixed_volume(
            plan or _plan(),
            account or _account(),
            _symbol(),
            volume,
        ).reasons

    assert any("symbol" in reason for reason in reasons(plan=_plan(symbol="GBPUSD")))
    assert any("spread" in reason for reason in reasons(plan=_plan(spread_points=4.0)))
    assert any(
        "stale" in reason
        for reason in reasons(account=_account(market_data_age_seconds=301.0))
    )
    assert any(
        "reward/risk" in reason
        for reason in reasons(plan=_plan(take_profit=1.0005))
    )
    assert any(
        "open positions" in reason
        for reason in reasons(account=_account(open_position_count=1))
    )
    assert any("minimum volume" in reason for reason in reasons(volume=0.001))
    assert any("maximum volume" in reason for reason in reasons(volume=1.01))
    assert any("volume step" in reason for reason in reasons(volume=0.015))
    assert any(
        "maximum exposure" in reason
        for reason in reasons(account=_account(current_exposure_lots=0.5))
    )
    assert any(
        "maximum symbol exposure" in reason
        for reason in reasons(
            account=_account(symbol_exposure_lots=0.5),
            limits=RiskLimits(
                min_reward_risk_ratio=1.0,
                max_lot_size=1.0,
                max_exposure_lots=2.0,
                max_symbol_exposure_lots=1.0,
            ),
        )
    )