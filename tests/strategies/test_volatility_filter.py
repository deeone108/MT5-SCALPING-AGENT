from datetime import UTC, datetime

import pandas as pd

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper, TrendScalperConfig


def test_rejects_m1_atr_fraction_below_configured_volatility_limit() -> None:
    candles = pd.DataFrame(
        {
            "time": [datetime(2026, 1, 5, 12, tzinfo=UTC)],
            "close": [1.2],
            "ema_9": [1.1],
            "ema_21": [1.0],
            "rsi_14": [60.0],
            "atr_14": [0.0001],
            "macd": [0.2],
            "macd_signal": [0.1],
        }
    )
    market = MarketAnalysisInput(
        symbol="EURUSD",
        m1=candles,
        m5=candles,
        bid=1.2,
        ask=1.20002,
        point=0.00001,
        observed_at=datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    proposal = TrendScalper(TrendScalperConfig(min_m1_atr_fraction=0.0001)).propose(market)

    assert proposal.direction is TradeDirection.NO_TRADE
    assert "ATR fraction" in proposal.reasons[0]
