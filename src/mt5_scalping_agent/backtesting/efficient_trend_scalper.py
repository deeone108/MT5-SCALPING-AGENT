"""Constant-size causal strategy adapter for longer historical simulations."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from mt5_scalping_agent.backtesting.engine import TradeIntent
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.indicators import with_indicators
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper


class EfficientTrendScalperBacktestStrategy:
    """Evaluate precomputed indicators with constant-size causal input windows."""

    uses_latest_candle_only = True

    def __init__(
        self,
        symbol: str,
        m1_candles: pd.DataFrame,
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
        self._m1 = with_indicators(validate_ohlcv(m1_candles)).reset_index(drop=True)
        self._m5 = with_indicators(validate_ohlcv(m5_candles)).reset_index(drop=True)
        self._m1_positions = {timestamp: index for index, timestamp in enumerate(self._m1["time"])}
        self._m5_times = self._m5["time"].array
        self._point = point
        self._spread_points = spread_points
        self._strategy = strategy or TrendScalper()
        self.required_history_bars = getattr(self._strategy, "required_m1_bars", 1)

    def __call__(self, latest_m1: pd.DataFrame) -> TradeIntent | None:
        """Evaluate one M1 close using its latest fully completed M5 candle."""
        current_time = latest_m1["time"].iloc[-1]
        m1_position = self._m1_positions.get(current_time)
        if m1_position is None:
            raise ValueError(f"M1 timestamp is not present in strategy data: {current_time}")
        m1_start = max(0, m1_position - self.required_history_bars + 1)
        m1 = self._m1.iloc[m1_start : m1_position + 1]
        observed_at = current_time.to_pydatetime() + timedelta(minutes=1)
        completed_through = observed_at - timedelta(minutes=5)
        m5_position = self._m5_times.searchsorted(completed_through, side="right") - 1
        if m5_position < 0:
            return None
        m5 = self._m5.iloc[m5_position : m5_position + 1]
        close = float(m1["close"].iloc[-1])
        proposal = self._strategy.propose(
            MarketAnalysisInput(
                symbol=self._symbol,
                m1=m1,
                m5=m5,
                bid=close,
                ask=close + self._spread_points * self._point,
                point=self._point,
                observed_at=observed_at,
            )
        )
        return TradeIntent.from_signal(proposal)
