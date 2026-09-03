from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import SignalProposal, TradeDirection


def test_actionable_signal_requires_complete_valid_geometry() -> None:
    proposal = SignalProposal(
        symbol="EURUSD",
        direction=TradeDirection.BUY,
        strategy="test",
        generated_at=datetime.now(UTC),
        entry_price=1.2,
        stop_loss=1.199,
        take_profit=1.202,
    )

    intent = TradeIntent.from_signal(proposal)

    assert intent is not None
    assert intent.direction is TradeDirection.BUY
    assert intent.stop_loss == 1.199


def test_no_trade_signal_has_no_backtest_intent() -> None:
    proposal = SignalProposal(symbol="EURUSD", direction=TradeDirection.NO_TRADE, strategy="test", generated_at=datetime.now(UTC))

    assert TradeIntent.from_signal(proposal) is None


def test_rejects_incomplete_or_invalid_actionable_signal() -> None:
    with pytest.raises(ValidationError, match="require entry"):
        SignalProposal(symbol="EURUSD", direction=TradeDirection.SELL, strategy="test", generated_at=datetime.now(UTC))

    with pytest.raises(ValidationError, match="stop_loss"):
        SignalProposal(symbol="EURUSD", direction=TradeDirection.BUY, strategy="test", generated_at=datetime.now(UTC), entry_price=1.2, stop_loss=1.201, take_profit=1.202)
