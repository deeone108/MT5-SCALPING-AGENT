"""Frozen Strategy 18 London Asian-range failed-auction intent emitter."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from mt5_scalping_agent.backtesting.engine import EntryEconomicsConstraints, TradeIntent
from mt5_scalping_agent.domain import TradeDirection


@dataclass(frozen=True)
class LondonAsianRangeFailedAuctionConfig:
    pip_size: float
    stress_cost_pips: float
    maximum_spread_points: float
    asian_start: time = time(0)
    sweep_start: time = time(7)
    sweep_end: time = time(9)
    minimum_sweep_pips: float = 8.0
    reentry_pips: float = 1.0
    confirmation_bars: int = 3
    stop_buffer_pips: float = 1.0
    minimum_stop_pips: float = 8.0
    maximum_stop_pips: float = 25.0
    reward_risk: float = 2.0
    minimum_reward_pips: float = 16.0
    minimum_cost_adjusted_reward_risk: float = 1.5
    maximum_holding_minutes: int = 240


class LondonAsianRangeFailedAuctionStrategy:
    """Trade only a confirmed London failed auction back into the Asian range."""

    uses_latest_candle_only = True
    required_history_bars = 600

    def __init__(self, *, spread_points: float, config: LondonAsianRangeFailedAuctionConfig) -> None:
        if config.pip_size <= 0 or config.stress_cost_pips <= 0 or config.maximum_spread_points <= 0:
            raise ValueError("Strategy 18 costs and pip size must be positive")
        self._config = config
        self._spread_points = spread_points
        self._zone = ZoneInfo("Europe/London")
        self._emitted: set[date] = set()
        self._rejections: Counter[str] = Counter()

    @property
    def diagnostics(self) -> dict[str, int]:
        return dict(sorted(self._rejections.items()))

    def is_evaluation_time(self, timestamp: datetime) -> bool:
        """Avoid allocating history outside completed M5 London decision points."""
        if timestamp.tzinfo is None:
            raise ValueError("Strategy 18 requires timezone-aware candles")
        local = timestamp.astimezone(self._zone)
        return (
            local.weekday() < 5
            and local.minute % 5 == 4
            and time(7) <= local.time() < time(9, 15)
        )
    def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
        if history.empty:
            return None
        current = pd.Timestamp(history["time"].iloc[-1])
        if current.tzinfo is None:
            raise ValueError("Strategy 18 requires timezone-aware candles")
        local = current.to_pydatetime().astimezone(self._zone)
        if not self.is_evaluation_time(current.to_pydatetime()):
            return None
        if local.date() in self._emitted:
            return self._reject("daily_limit")
        frame = history.copy()
        frame["local"] = pd.to_datetime(frame["time"], utc=True).dt.tz_convert(self._zone)
        day = frame.loc[frame["local"].dt.date == local.date()].reset_index(drop=True)
        asian = day.loc[(day["local"].dt.time >= time(0)) & (day["local"].dt.time < time(6))]
        if len(asian) != 360 or not _consecutive(asian["time"]):
            return self._reject("incomplete_asian_range")
        completed = day.loc[(day["local"].dt.time >= time(7)) & (day["local"].dt.time <= local.time())]
        if len(completed) < 5 or not _consecutive(completed["time"]):
            return self._reject("incomplete_london_window")
        m5 = completed.set_index("local").resample("5min", label="left", closed="left").agg(
            open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), count=("close", "count")
        ).dropna()
        if m5.empty or int(m5["count"].iloc[-1]) != 5:
            return self._reject("incomplete_m5")
        high, low, pip = float(asian["high"].max()), float(asian["low"].min()), self._config.pip_size
        sweep_index, direction = self._first_sweep(m5, high, low, pip)
        if sweep_index is None:
            return self._reject("no_sweep")
        candidates = m5.iloc[sweep_index + 1:sweep_index + 1 + self._config.confirmation_bars]
        if not self._latest_confirmation(candidates, direction, high, low, pip):
            return self._reject("no_current_confirmation")
        sweep = m5.iloc[sweep_index]
        entry = float(day["close"].iloc[-1])
        stop = float(sweep["high"]) + self._config.stop_buffer_pips * pip if direction is TradeDirection.SELL else float(sweep["low"]) - self._config.stop_buffer_pips * pip
        risk = abs(entry - stop)
        reward = risk * self._config.reward_risk
        risk_pips, reward_pips = risk / pip, reward / pip
        adjusted = (reward_pips - self._config.stress_cost_pips) / (risk_pips + self._config.stress_cost_pips)
        if not self._config.minimum_stop_pips <= risk_pips <= self._config.maximum_stop_pips:
            return self._reject("stop_distance")
        if reward_pips < self._config.minimum_reward_pips or adjusted < self._config.minimum_cost_adjusted_reward_risk:
            return self._reject("reward_economics")
        if self._spread_points > self._config.maximum_spread_points:
            return self._reject("spread_gate")
        target = entry - reward if direction is TradeDirection.SELL else entry + reward
        self._emitted.add(local.date())
        return TradeIntent(direction=direction, stop_loss=stop, take_profit=target, target_reward_risk_multiple=2.0, maximum_holding_duration=timedelta(minutes=self._config.maximum_holding_minutes), maximum_candle_gap=timedelta(minutes=1), entry_economics=EntryEconomicsConstraints(minimum_risk_distance=self._config.minimum_stop_pips*pip, minimum_reward_distance=self._config.minimum_reward_pips*pip, reference_cost_distance=self._config.stress_cost_pips*pip, minimum_cost_adjusted_reward_risk=self._config.minimum_cost_adjusted_reward_risk, maximum_spread_points=self._config.maximum_spread_points, maximum_all_in_cost_distance=self._config.stress_cost_pips*pip, required_entry_delay_seconds=60.0))

    def _first_sweep(self, m5: pd.DataFrame, high: float, low: float, pip: float) -> tuple[int | None, TradeDirection | None]:
        for index, row in m5.iterrows():
            clock = index.time()
            if not (self._config.sweep_start <= clock < self._config.sweep_end):
                continue
            if float(row["close"]) >= high + self._config.minimum_sweep_pips*pip:
                return m5.index.get_loc(index), TradeDirection.SELL
            if float(row["close"]) <= low - self._config.minimum_sweep_pips*pip:
                return m5.index.get_loc(index), TradeDirection.BUY
        return None, None

    def _latest_confirmation(self, rows: pd.DataFrame, direction: TradeDirection | None, high: float, low: float, pip: float) -> bool:
        if direction is None or rows.empty:
            return False
        close = float(rows["close"].iloc[-1])
        if direction is TradeDirection.SELL:
            return close <= high - self._config.reentry_pips * pip
        return close >= low + self._config.reentry_pips * pip
    def _reject(self, reason: str) -> None:
        self._rejections[reason] += 1
        return None


def _consecutive(times: pd.Series) -> bool:
    values = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    return len(values) > 0 and values.equals(pd.date_range(values[0], periods=len(values), freq="min"))
