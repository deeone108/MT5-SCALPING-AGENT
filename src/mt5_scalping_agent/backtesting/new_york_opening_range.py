"""Pre-specified New York opening-range breakout research baseline."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import time
import pandas as pd
from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import TradeDirection

@dataclass(frozen=True)
class NewYorkOpeningRangeConfig:
    range_start_utc: time = time(12)
    range_end_utc: time = time(13)
    entry_end_utc: time = time(17)
    target_reward_risk_ratio: float = 2.0

class NewYorkOpeningRangeBreakoutStrategy:
    """One daily New York range break, aligned with the 20-bar mean direction."""
    uses_latest_candle_only=True; required_history_bars=21
    def __init__(self, config: NewYorkOpeningRangeConfig=NewYorkOpeningRangeConfig()) -> None:
        if config.target_reward_risk_ratio <= 0: raise ValueError('target_reward_risk_ratio must be positive')
        self._config=config; self._day=None; self._range_high=None; self._range_low=None; self._traded=False
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        candle=history.iloc[-1]; timestamp=candle['time'].to_pydatetime()
        if timestamp.date() != self._day: self._day,self._range_high,self._range_low,self._traded=timestamp.date(),None,None,False
        current_time=timestamp.time()
        if self._config.range_start_utc <= current_time < self._config.range_end_utc:
            high,low=float(candle['high']),float(candle['low']); self._range_high=high if self._range_high is None else max(self._range_high,high); self._range_low=low if self._range_low is None else min(self._range_low,low); return None
        if self._traded or not (self._config.range_end_utc <= current_time < self._config.entry_end_utc): return None
        if self._range_high is None or self._range_low is None: return None
        close=float(candle['close']); slow_mean=float(history['close'].iloc[-20:].mean())
        if close > self._range_high and close > slow_mean:
            self._traded=True; risk=close-self._range_low; return TradeIntent(direction=TradeDirection.BUY,stop_loss=self._range_low,take_profit=close+risk*self._config.target_reward_risk_ratio)
        if close < self._range_low and close < slow_mean:
            self._traded=True; risk=self._range_high-close; return TradeIntent(direction=TradeDirection.SELL,stop_loss=self._range_high,take_profit=close-risk*self._config.target_reward_risk_ratio)
        return None