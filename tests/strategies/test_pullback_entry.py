from datetime import UTC, datetime

import pandas as pd

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper, TrendScalperConfig


def test_buy_pullback_requires_reclaim_of_m1_fast_ema() -> None:
    time = pd.to_datetime(["2026-01-05T11:59:00Z", "2026-01-05T12:00:00Z"])
    m1 = pd.DataFrame(
        {
            "time": time,
            "close": [1.099, 1.101],
            "ema_9": [1.100, 1.100],
            "ema_21": [1.098, 1.099],
            "rsi_14": [50.0, 60.0],
            "atr_14": [0.001, 0.001],
            "macd": [0.05, 0.2],
            "macd_signal": [0.1, 0.1],
        }
    )
    m5 = m1.iloc[[-1]].copy()
    market = MarketAnalysisInput(
        symbol="EURUSD",
        m1=m1,
        m5=m5,
        bid=1.101,
        ask=1.10102,
        point=0.00001,
        observed_at=datetime(2026, 1, 5, 12, 1, tzinfo=UTC),
    )

    proposal = TrendScalper(TrendScalperConfig(require_m1_pullback=True)).propose(market)

    assert proposal.direction is TradeDirection.BUY
