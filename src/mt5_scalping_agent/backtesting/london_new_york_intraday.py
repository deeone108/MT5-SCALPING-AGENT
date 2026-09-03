"""Frozen Strategy 17 London-to-New-York intraday continuation emitter."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from mt5_scalping_agent.backtesting.engine import EntryEconomicsConstraints, TradeIntent
from mt5_scalping_agent.domain import TradeDirection


@dataclass(frozen=True)
class LondonNewYorkIntradayConfig:
    pip_size: float = 0.0001
    timezone: str = "Europe/London"
    required_start_local: time = time(6)
    signal_time_local: time = time(11)
    minimum_impulse_pips: float = 25.0
    minimum_impulse_efficiency: float = 0.60
    maximum_pullback_fraction: float = 0.40
    minimum_reclaim_fraction: float = 0.80
    stop_buffer_pips: float = 1.0
    minimum_stop_pips: float = 12.0
    maximum_stop_pips: float = 35.0
    target_reward_risk_multiple: float = 2.0
    minimum_reward_pips: float = 30.0
    stress_reference_cost_pips: float = 0.9
    minimum_cost_adjusted_reward_risk: float = 1.5
    maximum_spread_points: float = 3.0
    maximum_all_in_cost_pips: float = 0.9
    maximum_holding_minutes: int = 300

    def __post_init__(self) -> None:
        numeric = tuple(self.__dict__[key] for key in self.__dict__ if key not in {"timezone", "required_start_local", "signal_time_local"})
        if any(not isfinite(float(value)) or float(value) <= 0 for value in numeric):
            raise ValueError("Strategy 17 numeric parameters must be finite and positive")
        if not 0 < self.minimum_impulse_efficiency <= 1 or not 0 < self.maximum_pullback_fraction <= 1 or not 0 < self.minimum_reclaim_fraction <= 1:
            raise ValueError("Strategy 17 fractions must be in (0, 1]")
        if self.minimum_stop_pips > self.maximum_stop_pips:
            raise ValueError("minimum stop cannot exceed maximum stop")
        ZoneInfo(self.timezone)


@dataclass(frozen=True)
class LondonNewYorkIntradayDiagnostics:
    evaluated_dates: int
    eligible_signal_count: int
    emitted_signal_count: int
    rejected_setup_counts: dict[str, int]


class LondonNewYorkIntradayContinuationStrategy:
    """At 11:00 London, trade a retained four-hour London impulse for up to five hours."""

    uses_latest_candle_only = True
    required_history_bars = 301

    def __init__(self, *, spread_points: float, all_in_cost_pips: float, config: LondonNewYorkIntradayConfig = LondonNewYorkIntradayConfig()) -> None:
        if not isfinite(spread_points) or spread_points < 0 or not isfinite(all_in_cost_pips) or all_in_cost_pips < 0:
            raise ValueError("cost inputs must be finite and nonnegative")
        self._config, self._spread_points, self._all_in_cost_pips = config, float(spread_points), float(all_in_cost_pips)
        self._zone = ZoneInfo(config.timezone)
        self._emitted_dates: set[date] = set()
        self._evaluated = self._eligible = self._emitted = 0
        self._rejections: Counter[str] = Counter()

    @property
    def diagnostics(self) -> LondonNewYorkIntradayDiagnostics:
        return LondonNewYorkIntradayDiagnostics(self._evaluated, self._eligible, self._emitted, dict(sorted(self._rejections.items())))

    def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
        if history.empty or "time" not in history:
            return None
        current = pd.Timestamp(history["time"].iloc[-1])
        if current.tzinfo is None:
            raise ValueError("Strategy 17 requires timezone-aware UTC candles")
        local = current.to_pydatetime().astimezone(self._zone)
        if local.time().replace(tzinfo=None) != self._config.signal_time_local:
            return None
        self._evaluated += 1
        if local.weekday() >= 5 or len(history) != self.required_history_bars:
            return self._reject("ineligible_or_incomplete_window")
        if local.date() in self._emitted_dates:
            return self._reject("daily_limit")
        frame = history.reset_index(drop=True)
        if not self._exact_window(frame, local.date()):
            return self._reject("nonconsecutive_required_window")
        values = frame[["open", "high", "low", "close"]].astype(float)
        if not values.map(isfinite).to_numpy().all():
            return self._reject("nonfinite_price")
        impulse, pullback = values.iloc[:240], values.iloc[240:301]
        start, impulse_close, final_close = float(impulse["open"].iloc[0]), float(impulse["close"].iloc[-1]), float(pullback["close"].iloc[-1])
        displacement, full_range = impulse_close - start, float(impulse["high"].max() - impulse["low"].min())
        magnitude, pip = abs(displacement), self._config.pip_size
        if magnitude < self._config.minimum_impulse_pips * pip:
            return self._reject("impulse_size")
        if full_range <= 0 or magnitude / full_range < self._config.minimum_impulse_efficiency:
            return self._reject("impulse_efficiency")
        direction = TradeDirection.BUY if displacement > 0 else TradeDirection.SELL
        adverse = impulse_close - float(pullback["low"].min()) if direction is TradeDirection.BUY else float(pullback["high"].max()) - impulse_close
        retained = final_close - start if direction is TradeDirection.BUY else start - final_close
        if adverse > self._config.maximum_pullback_fraction * magnitude:
            return self._reject("pullback_depth")
        if retained < self._config.minimum_reclaim_fraction * magnitude:
            return self._reject("reclaim")
        buffer = self._config.stop_buffer_pips * pip
        stop = float(pullback["low"].min()) - buffer if direction is TradeDirection.BUY else float(pullback["high"].max()) + buffer
        risk = final_close - stop if direction is TradeDirection.BUY else stop - final_close
        target = final_close + risk * self._config.target_reward_risk_multiple if direction is TradeDirection.BUY else final_close - risk * self._config.target_reward_risk_multiple
        risk_pips, reward_pips = risk / pip, risk * self._config.target_reward_risk_multiple / pip
        adjusted = (reward_pips - self._config.stress_reference_cost_pips) / (risk_pips + self._config.stress_reference_cost_pips)
        if not self._config.minimum_stop_pips <= risk_pips <= self._config.maximum_stop_pips:
            return self._reject("stop_distance")
        if reward_pips < self._config.minimum_reward_pips or adjusted < self._config.minimum_cost_adjusted_reward_risk:
            return self._reject("reward_economics")
        if self._spread_points > self._config.maximum_spread_points or self._all_in_cost_pips > self._config.maximum_all_in_cost_pips:
            return self._reject("cost_gate")
        self._eligible += 1; self._emitted += 1; self._emitted_dates.add(local.date())
        return TradeIntent(direction=direction, stop_loss=stop, take_profit=target, target_reward_risk_multiple=self._config.target_reward_risk_multiple, maximum_holding_duration=timedelta(minutes=self._config.maximum_holding_minutes), maximum_candle_gap=timedelta(minutes=1), entry_economics=EntryEconomicsConstraints(minimum_risk_distance=self._config.minimum_stop_pips*pip, minimum_reward_distance=self._config.minimum_reward_pips*pip, reference_cost_distance=self._config.stress_reference_cost_pips*pip, minimum_cost_adjusted_reward_risk=self._config.minimum_cost_adjusted_reward_risk, maximum_spread_points=self._config.maximum_spread_points, maximum_all_in_cost_distance=self._config.maximum_all_in_cost_pips*pip, required_entry_delay_seconds=60.0))

    def _exact_window(self, frame: pd.DataFrame, local_date: date) -> bool:
        start = pd.Timestamp.combine(local_date, self._config.required_start_local).tz_localize(self._zone)
        expected = pd.date_range(start=start, periods=self.required_history_bars, freq="min").tz_convert("UTC")
        return pd.DatetimeIndex(pd.to_datetime(frame["time"], utc=True)).equals(expected)

    def _reject(self, reason: str) -> None:
        self._rejections[reason] += 1
        return None
