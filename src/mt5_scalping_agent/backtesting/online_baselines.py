"""Additional public-rule baselines for historical research only."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import time
import pandas as pd
from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import TradeDirection

@dataclass(frozen=True)
class NewYorkOpeningRangeRetestConfig:
    range_start_utc: time = time(12)
    range_end_utc: time = time(12, 30)
    entry_end_utc: time = time(17)
    target_reward_risk_ratio: float = 2.0

class NewYorkOpeningRangeRetestStrategy:
    """One New York opening-range break, retest, and re-break with trend confirmation."""
    uses_latest_candle_only=True; required_history_bars=21
    def __init__(self, config: NewYorkOpeningRangeRetestConfig=NewYorkOpeningRangeRetestConfig()) -> None:
        if config.target_reward_risk_ratio <= 0: raise ValueError('target_reward_risk_ratio must be positive')
        self._config=config; self._day=None; self._high=None; self._low=None; self._break=None; self._retested=False; self._traded=False
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        candle=history.iloc[-1]; timestamp=candle['time'].to_pydatetime(); now=timestamp.time()
        if timestamp.date() != self._day: self._day,self._high,self._low,self._break,self._retested,self._traded=timestamp.date(),None,None,None,False,False
        if self._config.range_start_utc <= now < self._config.range_end_utc:
            high,low=float(candle.high),float(candle.low); self._high=high if self._high is None else max(self._high,high); self._low=low if self._low is None else min(self._low,low); return None
        if self._traded or not (self._config.range_end_utc <= now < self._config.entry_end_utc) or self._high is None or self._low is None: return None
        close=float(candle.close); slow=float(history.close.iloc[-20:].mean())
        if self._break is None:
            if close > self._high: self._break=TradeDirection.BUY
            elif close < self._low: self._break=TradeDirection.SELL
            return None
        if self._break is TradeDirection.BUY:
            if not self._retested and float(candle.low) <= self._high: self._retested=True; return None
            if self._retested and close > self._high and close > slow:
                self._traded=True; risk=close-self._low; return TradeIntent(direction=TradeDirection.BUY,stop_loss=self._low,take_profit=close+2*risk)
        else:
            if not self._retested and float(candle.high) >= self._low: self._retested=True; return None
            if self._retested and close < self._low and close < slow:
                self._traded=True; risk=self._high-close; return TradeIntent(direction=TradeDirection.SELL,stop_loss=self._high,take_profit=close-2*risk)
        return None

class PreviousDayRangeBreakoutStrategy:
    """One trade on a break of the completed prior UTC day's range."""
    uses_latest_candle_only=True; required_history_bars=1
    def __init__(self) -> None:
        self._day=None; self._current_high=None; self._current_low=None; self._previous=None; self._traded=False
    def __call__(self, latest: pd.DataFrame) -> TradeIntent|None:
        candle=latest.iloc[-1]; timestamp=candle['time'].to_pydatetime(); high,low,close=float(candle.high),float(candle.low),float(candle.close)
        if timestamp.date() != self._day:
            if self._day is not None: self._previous=(self._current_high,self._current_low)
            self._day,self._current_high,self._current_low,self._traded=timestamp.date(),high,low,False
        else:
            self._current_high=max(self._current_high,high); self._current_low=min(self._current_low,low)
        if self._previous is None or self._traded or not time(7) <= timestamp.time() < time(17): return None
        prior_high,prior_low=self._previous
        if close > prior_high:
            self._traded=True; risk=close-prior_low; return TradeIntent(direction=TradeDirection.BUY,stop_loss=prior_low,take_profit=close+2*risk)
        if close < prior_low:
            self._traded=True; risk=prior_high-close; return TradeIntent(direction=TradeDirection.SELL,stop_loss=prior_high,take_profit=close-2*risk)
        return None