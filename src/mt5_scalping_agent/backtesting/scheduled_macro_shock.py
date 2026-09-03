"""Scheduled U.S. macro-clock shock continuation research strategy."""

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
class ScheduledMacroShockConfig:
    pip_size: float = 0.0001
    timezone: str = "America/New_York"
    required_start_local: time = time(7, 30)
    signal_time_local: time = time(8, 39)
    baseline_m5_bars: int = 12
    minimum_shock_displacement_pips: float = 7.0
    minimum_shock_baseline_range_multiple: float = 2.0
    baseline_range_quantile: float = 0.90
    minimum_directional_efficiency: float = 0.70
    maximum_adverse_excursion_fraction: float = 0.20
    minimum_intrastabilization_retained_fraction: float = 0.50
    maximum_stabilization_retracement_fraction: float = 0.40
    minimum_final_retained_fraction: float = 0.70
    minimum_reacceleration_pips: float = 0.5
    stop_buffer_pips: float = 0.5
    minimum_stop_pips: float = 5.0
    maximum_stop_pips: float = 15.0
    target_reward_risk_multiple: float = 2.25
    minimum_reward_pips: float = 8.0
    stress_reference_cost_pips: float = 1.9
    minimum_cost_adjusted_reward_risk: float = 1.25
    maximum_spread_points: float = 10.0
    maximum_all_in_cost_pips: float = 1.9
    maximum_holding_minutes: int = 80

    def __post_init__(self) -> None:
        positive = (
            self.pip_size,
            self.baseline_m5_bars,
            self.minimum_shock_displacement_pips,
            self.minimum_shock_baseline_range_multiple,
            self.baseline_range_quantile,
            self.minimum_directional_efficiency,
            self.maximum_adverse_excursion_fraction,
            self.minimum_intrastabilization_retained_fraction,
            self.maximum_stabilization_retracement_fraction,
            self.minimum_final_retained_fraction,
            self.minimum_reacceleration_pips,
            self.stop_buffer_pips,
            self.minimum_stop_pips,
            self.maximum_stop_pips,
            self.target_reward_risk_multiple,
            self.minimum_reward_pips,
            self.stress_reference_cost_pips,
            self.minimum_cost_adjusted_reward_risk,
            self.maximum_spread_points,
            self.maximum_all_in_cost_pips,
            self.maximum_holding_minutes,
        )
        if any(not isfinite(float(value)) or float(value) <= 0 for value in positive):
            raise ValueError("Strategy 16 numeric parameters must be finite and positive")
        fractions = (
            self.baseline_range_quantile,
            self.minimum_directional_efficiency,
            self.maximum_adverse_excursion_fraction,
            self.minimum_intrastabilization_retained_fraction,
            self.maximum_stabilization_retracement_fraction,
            self.minimum_final_retained_fraction,
        )
        if any(value > 1 for value in fractions):
            raise ValueError("Strategy 16 fractions and quantiles cannot exceed one")
        if self.minimum_stop_pips > self.maximum_stop_pips:
            raise ValueError("minimum stop cannot exceed maximum stop")
        ZoneInfo(self.timezone)


@dataclass(frozen=True)
class ScheduledMacroShockDiagnostics:
    evaluated_event_dates: int
    eligible_signal_count: int
    emitted_signal_count: int
    daily_limit_block_count: int
    rejected_setup_counts: dict[str, int]


class ScheduledMacroShockContinuationStrategy:
    """Trade retained 08:30 New York shock direction after ten observed minutes."""

    uses_latest_candle_only = True
    required_history_bars = 70

    def __init__(
        self,
        *,
        spread_points: float,
        all_in_cost_pips: float,
        config: ScheduledMacroShockConfig = ScheduledMacroShockConfig(),
    ) -> None:
        if not isfinite(spread_points) or spread_points < 0:
            raise ValueError("spread_points must be finite and nonnegative")
        if not isfinite(all_in_cost_pips) or all_in_cost_pips < 0:
            raise ValueError("all_in_cost_pips must be finite and nonnegative")
        self._config = config
        self._spread_points = float(spread_points)
        self._all_in_cost_pips = float(all_in_cost_pips)
        self._ny = ZoneInfo(config.timezone)
        self._emitted_dates: set[date] = set()
        self._evaluated = 0
        self._eligible = 0
        self._emitted = 0
        self._daily_blocks = 0
        self._rejections: Counter[str] = Counter()

    @property
    def diagnostics(self) -> ScheduledMacroShockDiagnostics:
        return ScheduledMacroShockDiagnostics(
            evaluated_event_dates=self._evaluated,
            eligible_signal_count=self._eligible,
            emitted_signal_count=self._emitted,
            daily_limit_block_count=self._daily_blocks,
            rejected_setup_counts=dict(sorted(self._rejections.items())),
        )

    def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
        if history.empty or "time" not in history:
            return None
        timestamp = pd.Timestamp(history["time"].iloc[-1])
        if timestamp.tzinfo is None:
            raise ValueError("Strategy 16 requires timezone-aware UTC candles")
        local = timestamp.to_pydatetime().astimezone(self._ny)
        if local.time().replace(tzinfo=None) != self._config.signal_time_local:
            return None
        self._evaluated += 1
        local_date = local.date()
        if local.weekday() >= 5:
            return self._reject("weekend")
        if local_date in self._emitted_dates:
            self._daily_blocks += 1
            return self._reject("daily_limit")
        if len(history) != self.required_history_bars:
            return self._reject("incomplete_required_window")

        frame = history.reset_index(drop=True)
        if not self._has_exact_required_minutes(frame, local_date):
            return self._reject("nonconsecutive_required_window")
        values = frame[["open", "high", "low", "close"]].astype(float)
        if not values.map(isfinite).to_numpy().all():
            return self._reject("nonfinite_price")

        baseline = values.iloc[:60]
        shock = values.iloc[60:65]
        stabilization = values.iloc[65:70]
        baseline_ranges = pd.Series(
            [
                float(baseline.iloc[offset : offset + 5]["high"].max())
                - float(baseline.iloc[offset : offset + 5]["low"].min())
                for offset in range(0, 60, 5)
            ],
            dtype="float64",
        )
        if len(baseline_ranges) != self._config.baseline_m5_bars:
            return self._reject("baseline_shape")
        median_range = float(baseline_ranges.median())
        q90_range = float(
            baseline_ranges.quantile(
                self._config.baseline_range_quantile,
                interpolation="linear",
            )
        )
        if median_range <= 0 or q90_range <= 0:
            return self._reject("nonpositive_baseline_range")

        p0 = float(baseline["close"].iloc[-1])
        shock_close = float(shock["close"].iloc[-1])
        shock_high = float(shock["high"].max())
        shock_low = float(shock["low"].min())
        displacement = shock_close - p0
        magnitude = abs(displacement)
        shock_range = shock_high - shock_low
        pip = self._config.pip_size
        if magnitude + 1e-12 < self._config.minimum_shock_displacement_pips * pip:
            return self._reject("shock_displacement")
        minimum_range = max(
            self._config.minimum_shock_baseline_range_multiple * median_range,
            q90_range,
        )
        if shock_range + 1e-12 < minimum_range:
            return self._reject("shock_range_abnormality")
        if shock_range <= 0 or magnitude / shock_range + 1e-12 < self._config.minimum_directional_efficiency:
            return self._reject("directional_efficiency")

        direction = TradeDirection.BUY if displacement > 0 else TradeDirection.SELL
        adverse = p0 - shock_low if direction is TradeDirection.BUY else shock_high - p0
        if adverse > self._config.maximum_adverse_excursion_fraction * shock_range + 1e-12:
            return self._reject("adverse_shock_excursion")

        closes = stabilization["close"].astype(float)
        final_close = float(closes.iloc[-1])
        reference_close = float(closes.iloc[2])  # Exact 08:37 close.
        if direction is TradeDirection.BUY:
            retention_floor = p0 + self._config.minimum_intrastabilization_retained_fraction * magnitude
            if bool((closes < retention_floor - 1e-12).any()):
                return self._reject("intrastabilization_retention")
            retracement = shock_close - float(stabilization["low"].min())
            retained = final_close - p0
            reacceleration = final_close - reference_close
        else:
            retention_ceiling = p0 - self._config.minimum_intrastabilization_retained_fraction * magnitude
            if bool((closes > retention_ceiling + 1e-12).any()):
                return self._reject("intrastabilization_retention")
            retracement = float(stabilization["high"].max()) - shock_close
            retained = p0 - final_close
            reacceleration = reference_close - final_close
        if retracement > self._config.maximum_stabilization_retracement_fraction * magnitude + 1e-12:
            return self._reject("stabilization_retracement")
        if retained + 1e-12 < self._config.minimum_final_retained_fraction * magnitude:
            return self._reject("final_retention")
        if reacceleration + 1e-12 < self._config.minimum_reacceleration_pips * pip:
            return self._reject("reacceleration")

        half_level = p0 + (0.5 * magnitude if direction is TradeDirection.BUY else -0.5 * magnitude)
        buffer_distance = self._config.stop_buffer_pips * pip
        if direction is TradeDirection.BUY:
            stop = min(float(stabilization["low"].min()), half_level) - buffer_distance
            risk = final_close - stop
            target = final_close + risk * self._config.target_reward_risk_multiple
        else:
            stop = max(float(stabilization["high"].max()), half_level) + buffer_distance
            risk = stop - final_close
            target = final_close - risk * self._config.target_reward_risk_multiple
        risk_pips = risk / pip
        reward_pips = risk_pips * self._config.target_reward_risk_multiple
        adjusted = (
            reward_pips - self._config.stress_reference_cost_pips
        ) / (risk_pips + self._config.stress_reference_cost_pips)
        if risk_pips + 1e-12 < self._config.minimum_stop_pips:
            return self._reject("minimum_stop")
        if risk_pips > self._config.maximum_stop_pips + 1e-12:
            return self._reject("maximum_stop")
        if reward_pips + 1e-12 < self._config.minimum_reward_pips:
            return self._reject("minimum_reward")
        if adjusted + 1e-12 < self._config.minimum_cost_adjusted_reward_risk:
            return self._reject("cost_adjusted_reward_risk")
        if self._spread_points > self._config.maximum_spread_points + 1e-12:
            return self._reject("spread_gate")
        if self._all_in_cost_pips > self._config.maximum_all_in_cost_pips + 1e-12:
            return self._reject("all_in_cost_gate")

        self._eligible += 1
        self._emitted += 1
        self._emitted_dates.add(local_date)
        return TradeIntent(
            direction=direction,
            stop_loss=stop,
            take_profit=target,
            target_reward_risk_multiple=self._config.target_reward_risk_multiple,
            maximum_holding_duration=timedelta(minutes=self._config.maximum_holding_minutes),
            maximum_candle_gap=timedelta(minutes=1),
            entry_economics=EntryEconomicsConstraints(
                minimum_risk_distance=self._config.minimum_stop_pips * pip,
                minimum_reward_distance=self._config.minimum_reward_pips * pip,
                reference_cost_distance=self._config.stress_reference_cost_pips * pip,
                minimum_cost_adjusted_reward_risk=self._config.minimum_cost_adjusted_reward_risk,
                maximum_spread_points=self._config.maximum_spread_points,
                maximum_all_in_cost_distance=self._config.maximum_all_in_cost_pips * pip,
                required_entry_delay_seconds=60.0,
            ),
        )

    def _has_exact_required_minutes(self, frame: pd.DataFrame, local_date: date) -> bool:
        times = pd.to_datetime(frame["time"], utc=True)
        start = pd.Timestamp.combine(local_date, self._config.required_start_local).tz_localize(self._ny)
        expected = pd.date_range(start=start, periods=self.required_history_bars, freq="min").tz_convert("UTC")
        observed = pd.DatetimeIndex(times)
        return observed.equals(expected)

    def _reject(self, reason: str) -> None:
        self._rejections[reason] += 1
        return None