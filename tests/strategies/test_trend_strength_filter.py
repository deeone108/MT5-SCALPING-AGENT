from datetime import UTC, datetime

import pandas as pd

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper, TrendScalperConfig


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [datetime(2026, 1, 5, 12, tzinfo=UTC)],
            "close": [1.2],
            "ema_9": [1.001],
            "ema_21": [1.0],
            "rsi_14": [60.0],
            "atr_14": [0.01],
            "macd": [0.2],
            "macd_signal": [0.1],
        }
    )


def test_rejects_m5_trend_below_configured_atr_relative_strength() -> None:
    candles = frame()
    market = MarketAnalysisInput(
        symbol="EURUSD",
        m1=candles,
        m5=candles,
        bid=1.2,
        ask=1.20002,
        point=0.00001,
        observed_at=datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    proposal = TrendScalper(TrendScalperConfig(min_m5_trend_strength=0.2)).propose(market)

    assert proposal.direction is TradeDirection.NO_TRADE
    assert "trend strength" in proposal.reasons[0]
