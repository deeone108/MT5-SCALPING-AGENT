from datetime import UTC, datetime

import pandas as pd
import pytest

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper, TrendScalperConfig


OBSERVED_AT = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def frame(*, bullish: bool = True, rsi: float = 60.0, timestamp: datetime = OBSERVED_AT) -> pd.DataFrame:
    trend = 1.2 if bullish else 1.0
    return pd.DataFrame(
        {
            "time": [timestamp],
            "close": [trend],
            "ema_9": [1.1 if bullish else 0.9],
            "ema_21": [1.0],
            "rsi_14": [rsi],
            "atr_14": [0.001],
            "macd": [0.2 if bullish else -0.2],
            "macd_signal": [0.1 if bullish else -0.1],
        }
    )


def market(*, m1: pd.DataFrame | None = None, m5: pd.DataFrame | None = None, ask: float = 1.20002, bid: float = 1.2) -> MarketAnalysisInput:
    return MarketAnalysisInput(
        symbol="EURUSD",
        m1=m1 if m1 is not None else frame(),
        m5=m5 if m5 is not None else frame(),
        bid=bid,
        ask=ask,
        point=0.00001,
        observed_at=OBSERVED_AT,
    )


def test_proposes_buy_with_atr_stop_and_target() -> None:
    proposal = TrendScalper().propose(market())

    assert proposal.direction is TradeDirection.BUY
    assert proposal.entry_price == 1.20002
    assert proposal.stop_loss == pytest.approx(1.19902)
    assert proposal.take_profit == pytest.approx(1.20202)


def test_proposes_sell_with_atr_stop_and_target() -> None:
    proposal = TrendScalper().propose(market(m1=frame(bullish=False, rsi=40), m5=frame(bullish=False, rsi=40)))

    assert proposal.direction is TradeDirection.SELL
    assert proposal.entry_price == 1.2
    assert proposal.stop_loss == pytest.approx(1.201)
    assert proposal.take_profit == pytest.approx(1.198)


def test_rejects_excessive_spread() -> None:
    proposal = TrendScalper().propose(market(ask=1.20005))

    assert proposal.direction is TradeDirection.NO_TRADE
    assert "spread" in proposal.reasons[0]


def test_rejects_stale_data() -> None:
    stale = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    proposal = TrendScalper().propose(market(m1=frame(timestamp=stale), m5=frame(timestamp=stale)))

    assert proposal.direction is TradeDirection.NO_TRADE
    assert "stale" in proposal.reasons[0]


def test_rejects_incomplete_indicator_warmup() -> None:
    incomplete = frame()
    incomplete.loc[0, "rsi_14"] = float("nan")

    proposal = TrendScalper().propose(market(m1=incomplete))

    assert proposal.direction is TradeDirection.NO_TRADE
    assert "warm-up" in proposal.reasons[0]


def test_rejects_outside_session() -> None:
    input_data = market()
    night = MarketAnalysisInput(**{**input_data.__dict__, "observed_at": datetime(2026, 1, 5, 23, tzinfo=UTC)})

    proposal = TrendScalper().propose(night)

    assert proposal.direction is TradeDirection.NO_TRADE
    assert proposal.reasons == ("outside configured trading session",)


def test_rejects_invalid_strategy_configuration() -> None:
    with pytest.raises(ValueError, match="buy RSI"):
        TrendScalperConfig(buy_rsi_minimum=71, buy_rsi_maximum=70)
