"""Causal M1/M5 adapter for backtesting the trend scalper."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from mt5_scalping_agent.backtesting.engine import TradeIntent
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.indicators import with_indicators
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper


class TrendScalperBacktestStrategy:
    """Adapt ``TrendScalper`` to a candle callback without future M5 bars."""

    def __init__(
        self,
        symbol: str,
        m5_candles: pd.DataFrame,
        point: float,
        spread_points: float = 0.0,
        strategy: TrendScalper | None = None,
    ) -> None:
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        if point <= 0:
            raise ValueError("point must be greater than zero")
        if spread_points < 0:
            raise ValueError("spread_points must not be negative")

        self._symbol = symbol
        self._m5 = with_indicators(validate_ohlcv(m5_candles))
        self._point = point
        self._spread_points = spread_points
        self._strategy = strategy or TrendScalper()

    def __call__(self, m1_history: pd.DataFrame) -> TradeIntent | None:
        """Return a simulated intent based only on candles closed by this M1 close."""
        m1 = with_indicators(validate_ohlcv(m1_history))
        observed_at = m1["time"].iloc[-1].to_pydatetime() + timedelta(minutes=1)
        completed_m5 = self._m5.loc[self._m5["time"] + timedelta(minutes=5) <= observed_at].copy()
        if completed_m5.empty:
            return None

        close = float(m1["close"].iloc[-1])
        proposal = self._strategy.propose(
            MarketAnalysisInput(
                symbol=self._symbol,
                m1=m1,
                m5=completed_m5,
                bid=close,
                ask=close + self._spread_points * self._point,
                point=self._point,
                observed_at=observed_at,
            )
        )
        return TradeIntent.from_signal(proposal)
