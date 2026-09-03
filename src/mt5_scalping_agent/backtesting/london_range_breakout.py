"""Pre-specified London session range-breakout research baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import TradeDirection


@dataclass(frozen=True)
class LondonRangeBreakoutConfig:
    range_start_utc: time = time(0)
    breakout_start_utc: time = time(7)
    breakout_end_utc: time = time(12)
    target_reward_risk_ratio: float = 2.0


class LondonRangeBreakoutStrategy:
    """One daily trade on a London-session break of the completed Asian range."""

    uses_latest_candle_only = True
    required_history_bars = 1

    def __init__(self, config: LondonRangeBreakoutConfig = LondonRangeBreakoutConfig()) -> None:
        if config.target_reward_risk_ratio <= 0:
            raise ValueError("target_reward_risk_ratio must be positive")
        self._config = config
        self._day = None
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._traded = False

    def __call__(self, latest: pd.DataFrame) -> TradeIntent | None:
        candle = latest.iloc[-1]
        timestamp = candle["time"].to_pydatetime()
        if timestamp.date() != self._day:
            self._day, self._range_high, self._range_low, self._traded = timestamp.date(), None, None, False
        current_time = timestamp.time()
        if self._config.range_start_utc <= current_time < self._config.breakout_start_utc:
            self._range_high = max(self._range_high, float(candle["high"])) if self._range_high is not None else float(candle["high"])
            self._range_low = min(self._range_low, float(candle["low"])) if self._range_low is not None else float(candle["low"])
            return None
        if self._traded or not (self._config.breakout_start_utc <= current_time < self._config.breakout_end_utc):
            return None
        if self._range_high is None or self._range_low is None:
            return None
        close, width = float(candle["close"]), self._range_high - self._range_low
        if width <= 0:
            return None
        if close > self._range_high:
            self._traded = True
            return TradeIntent(direction=TradeDirection.BUY, stop_loss=self._range_low, take_profit=close + (close - self._range_low) * self._config.target_reward_risk_ratio)
        if close < self._range_low:
            self._traded = True
            return TradeIntent(direction=TradeDirection.SELL, stop_loss=self._range_high, take_profit=close - (self._range_high - close) * self._config.target_reward_risk_ratio)
        return None
