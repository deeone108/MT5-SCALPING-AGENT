import pytest

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.risk import AccountRiskState, RiskEngine, RiskLimits, SymbolRiskSpec, TradePlan


def symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )


def account(**changes: float | int) -> AccountRiskState:
    values = {
        "equity": 100_000.0,
        "balance": 100_000.0,
        "peak_equity": 100_000.0,
        "daily_realized_pnl": 0.0,
        "open_position_count": 0,
        "current_exposure_lots": 0.0,
        "consecutive_losses": 0,
    }
    values.update(changes)
    return AccountRiskState(**values)


def buy_plan(**changes: float) -> TradePlan:
    values = {
        "symbol": "EURUSD",
        "direction": TradeDirection.BUY,
        "entry_price": 1.20000,
        "stop_loss": 1.19800,
        "take_profit": 1.20400,
        "spread_points": 2.0,
    }
    values.update(changes)
    return TradePlan(**values)


def test_calculates_symbol_aware_position_size() -> None:
    engine = RiskEngine(RiskLimits(max_lot_size=10, max_exposure_lots=10))

    decision = engine.assess(buy_plan(), account(), symbol())

    assert decision.allowed is True
    assert decision.volume_lots == pytest.approx(2.5)
    assert decision.risk_amount == pytest.approx(500.0)
    assert decision.reward_risk_ratio == pytest.approx(2.0)


def test_caps_position_size_to_configured_lot_limit() -> None:
    decision = RiskEngine().assess(buy_plan(), account(), symbol())

    assert decision.allowed is True
    assert decision.volume_lots == 1.0
    assert decision.risk_amount == pytest.approx(200.0)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"spread_points": 4.0}, "spread"),
        ({"take_profit": 1.20200}, "reward/risk"),
    ],
)
def test_rejects_invalid_trade_conditions(changes: dict[str, float], reason: str) -> None:
    decision = RiskEngine().assess(buy_plan(**changes), account(), symbol())

    assert decision.allowed is False
    assert reason in decision.reasons[0]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"daily_realized_pnl": -2_000.0}, "daily loss"),
        ({"equity": 90_000.0}, "drawdown"),
        ({"consecutive_losses": 3}, "consecutive"),
        ({"open_position_count": 1}, "open positions"),
    ],
)
def test_rejects_account_protection_limits(changes: dict[str, float | int], reason: str) -> None:
    decision = RiskEngine().assess(buy_plan(), account(**changes), symbol())

    assert decision.allowed is False
    assert reason in decision.reasons[0]


def test_rejects_exposure_and_minimum_volume() -> None:
    exposure = RiskEngine().assess(buy_plan(), account(current_exposure_lots=0.5), symbol())
    too_small = RiskEngine(RiskLimits(risk_percent_per_trade=0.001)).assess(buy_plan(), account(), symbol())

    assert exposure.allowed is False
    assert "exposure" in exposure.reasons[0]
    assert too_small.allowed is False
    assert "minimum volume" in too_small.reasons[0]


def test_rejects_invalid_directional_prices_and_symbol_mismatch() -> None:
    with pytest.raises(ValueError, match="stop_loss"):
        buy_plan(stop_loss=1.201)

    decision = RiskEngine().assess(buy_plan(symbol="GBPUSD"), account(), symbol())
    assert decision.allowed is False
    assert "symbol" in decision.reasons[0]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"weekly_realized_pnl": -5_000.0}, "weekly loss"),
        ({"trades_current_hour": 20}, "trades per hour"),
        ({"trades_current_day": 100}, "trades per day"),
        ({"market_data_age_seconds": 301.0}, "stale"),
    ],
)
def test_rejects_weekly_rate_and_stale_data_limits(
    changes: dict[str, float | int], reason: str
) -> None:
    decision = RiskEngine().assess(buy_plan(), account(**changes), symbol())

    assert decision.allowed is False
    assert any(reason in item for item in decision.reasons)


def test_uses_frozen_period_start_equity_for_loss_limits() -> None:
    decision = RiskEngine().assess(
        buy_plan(),
        account(daily_realized_pnl=-1_000, daily_starting_equity=50_000),
        symbol(),
    )

    assert decision.allowed is False
    assert "daily loss" in decision.reasons[0]


def test_rejects_per_symbol_exposure_independently_of_total_exposure() -> None:
    limits = RiskLimits(
        max_lot_size=10,
        max_exposure_lots=10,
        max_symbol_exposure_lots=3,
    )
    decision = RiskEngine(limits).assess(
        buy_plan(),
        account(current_exposure_lots=1, symbol_exposure_lots=1),
        symbol(),
    )

    assert decision.allowed is False
    assert "symbol exposure" in decision.reasons[0]


def test_rejects_depleted_mark_to_market_equity() -> None:
    decision = RiskEngine().assess(buy_plan(), account(equity=0), symbol())

    assert decision.allowed is False
    assert "depleted" in decision.reasons[0]