"""Low-turnover New York exhaustion re-entry research baseline."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, time
import pandas as pd
from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import TradeDirection

@dataclass(frozen=True)
class NewYorkBollingerReentryConfig:
    session_start_utc: time = time(12)
    session_end_utc: time = time(17)
    reward_risk_ratio: float = 2.0
    atr_stop_multiplier: float = 1.0

class NewYorkBollingerReentryStrategy:
    """Take at most one daily reversal after an exhausted close re-enters its band."""
    uses_latest_candle_only = True
    required_history_bars = 22

    def __init__(self, config: NewYorkBollingerReentryConfig = NewYorkBollingerReentryConfig()) -> None:
        if config.reward_risk_ratio <= 0 or config.atr_stop_multiplier <= 0:
            raise ValueError("reward/risk ratio and ATR stop multiplier must be positive")
        self._config = config
        self._day: date | None = None
        self._traded = False

    def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
        timestamp = history["time"].iloc[-1].to_pydatetime()
        if timestamp.date() != self._day:
            self._day = timestamp.date()
            self._traded = False
        if self._traded or not (self._config.session_start_utc <= timestamp.time() < self._config.session_end_utc):
            return None
        closes = history["close"]
        previous_window, current_window = closes.iloc[-21:-1], closes.iloc[-20:]
        previous_mean, previous_std = float(previous_window.mean()), float(previous_window.std(ddof=0))
        current_mean, current_std = float(current_window.mean()), float(current_window.std(ddof=0))
        if previous_std <= 0 or current_std <= 0:
            return None
        changes = closes.diff().iloc[-14:]
        gains, losses = float(changes.clip(lower=0).mean()), float(-changes.clip(upper=0).mean())
        rsi = 100.0 if losses == 0 else (0.0 if gains == 0 else 100.0 - 100.0 / (1.0 + gains / losses))
        previous_closes = closes.shift(1)
        true_range = pd.concat([history["high"]-history["low"], (history["high"]-previous_closes).abs(), (history["low"]-previous_closes).abs()], axis=1).max(axis=1)
        atr = float(true_range.iloc[-14:].mean())
        if atr <= 0:
            return None
        previous_close, close = float(closes.iloc[-2]), float(closes.iloc[-1])
        risk = atr * self._config.atr_stop_multiplier
        previous_lower, current_lower = previous_mean-2*previous_std, current_mean-2*current_std
        previous_upper, current_upper = previous_mean+2*previous_std, current_mean+2*current_std
        if previous_close < previous_lower and close >= current_lower and rsi <= 30.0:
            self._traded = True
            return TradeIntent(direction=TradeDirection.BUY, stop_loss=close-risk, take_profit=close+risk*self._config.reward_risk_ratio)
        if previous_close > previous_upper and close <= current_upper and rsi >= 70.0:
            self._traded = True
            return TradeIntent(direction=TradeDirection.SELL, stop_loss=close+risk, take_profit=close-risk*self._config.reward_risk_ratio)
        return None