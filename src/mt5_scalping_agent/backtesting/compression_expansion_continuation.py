"""Pre-registered Strategy 15 compression/expansion continuation intent emitter."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time, timedelta
from math import isfinite
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd

from mt5_scalping_agent.backtesting.engine import EntryEconomicsConstraints, TradeIntent
from mt5_scalping_agent.data.validation import MarketDataValidationError, validate_ohlcv
from mt5_scalping_agent.domain import TradeDirection


@dataclass(frozen=True)
class CompressionExpansionControlledContinuationConfig:
    """Frozen Strategy 15 parameters; changes are separate research hypotheses."""

    pip_size: float = 0.0001
    compression_bars_m5: int = 12
    baseline_bars_m5: int = 48
    compression_baseline_quantile: float = 0.25
    maximum_compression_box_pips: float = 15.0
    context_sma_bars_m15: int = 20
    context_slope_lag_bars_m15: int = 4
    context_required_bars_m15: int = 24
    expansion_min_compression_range_multiple: float = 2.0
    expansion_min_baseline_quantile: float = 0.75
    expansion_max_baseline_median_multiple: float = 3.0
    expansion_min_body_fraction: float = 0.65
    expansion_max_close_edge_fraction: float = 0.20
    breakout_min_clearance_pips: float = 0.5
    breakout_max_extension_box_fraction: float = 0.50
    retest_max_bars: int = 3
    confirmation_max_bars_after_expansion: int = 4
    retest_outer_box_fraction: float = 0.20
    retest_inner_box_fraction: float = 0.25
    confirmation_min_body_fraction: float = 0.50
    confirmation_max_close_edge_fraction: float = 0.25
    confirmation_clearance_pips: float = 0.2
    stop_buffer_pips: float = 0.5
    target_box_multiple: float = 1.5
    stress_reference_cost_pips: float = 1.0
    minimum_stop_pips: float = 4.0
    minimum_reward_pips: float = 6.0
    minimum_cost_adjusted_reward_risk: float = 1.5
    maximum_spread_points: float = 4.0
    maximum_all_in_cost_pips: float = 1.0
    maximum_emitted_signals_per_ny_day: int = 2
    maximum_holding_minutes: int = 120
    expansion_start_local: time = time(8)
    expansion_end_local_exclusive: time = time(11, 30)
    confirmation_end_local_inclusive: time = time(12)
    timezone: str = "America/New_York"

    def __post_init__(self) -> None:
        positive = (
            self.pip_size,
            self.maximum_compression_box_pips,
            self.expansion_min_compression_range_multiple,
            self.expansion_max_baseline_median_multiple,
            self.breakout_min_clearance_pips,
            self.confirmation_clearance_pips,
            self.stop_buffer_pips,
            self.target_box_multiple,
            self.stress_reference_cost_pips,
            self.minimum_stop_pips,
            self.minimum_reward_pips,
            self.minimum_cost_adjusted_reward_risk,
            self.maximum_spread_points,
            self.maximum_all_in_cost_pips,
        )
        counts = (
            self.compression_bars_m5,
            self.baseline_bars_m5,
            self.context_sma_bars_m15,
            self.context_slope_lag_bars_m15,
            self.context_required_bars_m15,
            self.retest_max_bars,
            self.confirmation_max_bars_after_expansion,
            self.maximum_emitted_signals_per_ny_day,
            self.maximum_holding_minutes,
        )
        fractions = (
            self.compression_baseline_quantile,
            self.expansion_min_baseline_quantile,
            self.expansion_min_body_fraction,
            self.expansion_max_close_edge_fraction,
            self.breakout_max_extension_box_fraction,
            self.retest_outer_box_fraction,
            self.retest_inner_box_fraction,
            self.confirmation_min_body_fraction,
            self.confirmation_max_close_edge_fraction,
        )
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError("Strategy 15 positive parameters must be finite and positive")
        if not all(value > 0 for value in counts):
            raise ValueError("Strategy 15 bar counts and limits must be positive")
        if not all(isfinite(value) and 0 < value < 1 for value in fractions):
            raise ValueError("Strategy 15 fractions and quantiles must be between zero and one")
        if self.context_required_bars_m15 < (
            self.context_sma_bars_m15 + self.context_slope_lag_bars_m15
        ):
            raise ValueError("M15 context history is shorter than its SMA and slope lookback")
        if self.retest_max_bars >= self.confirmation_max_bars_after_expansion:
            raise ValueError("confirmation deadline must follow the retest deadline")
        if self.expansion_start_local >= self.expansion_end_local_exclusive:
            raise ValueError("expansion session must have positive duration")
        if self.expansion_end_local_exclusive > self.confirmation_end_local_inclusive:
            raise ValueError("confirmation cutoff cannot precede expansion cutoff")


@dataclass(frozen=True)
class CompressionExpansionDiagnostics:
    """Immutable accounting for causal setup recognition and intent emissions."""

    evaluated_expansion_bars: int
    eligible_setup_count: int
    eligible_signal_count: int
    emitted_signal_count: int
    daily_limit_block_count: int
    reused_setup_block_count: int
    rejected_setup_counts: Mapping[str, int]


@dataclass(frozen=True)
class _EligibleCandidate:
    setup_id: str
    expansion_time: pd.Timestamp
    confirmation_time: pd.Timestamp
    local_date: date
    direction: TradeDirection
    stop_loss: float
    take_profit: float


class CompressionExpansionControlledContinuationStrategy:
    """Emit frozen Strategy 15 intents from precomputed, completed causal bars."""

    uses_latest_candle_only = True
    required_history_bars = 1

    def __init__(
        self,
        m1_candles: pd.DataFrame,
        *,
        spread_points: float = 2.0,
        all_in_cost_pips: float = 0.7,
        config: CompressionExpansionControlledContinuationConfig | None = None,
    ) -> None:
        self._config = config or CompressionExpansionControlledContinuationConfig()
        if not isfinite(spread_points) or spread_points < 0:
            raise ValueError("spread_points must be finite and nonnegative")
        if not isfinite(all_in_cost_pips) or all_in_cost_pips < 0:
            raise ValueError("all_in_cost_pips must be finite and nonnegative")

        m1 = validate_ohlcv(m1_candles).reset_index(drop=True)
        if (m1["time"].dt.floor("min") != m1["time"]).any():
            raise MarketDataValidationError("Strategy 15 requires whole-minute M1 timestamps")
        self._m1_times = pd.DatetimeIndex(m1["time"])
        m5 = _strict_resample(m1, 5)
        m15 = _strict_resample(m1, 15)
        (
            self._candidates_by_latest_m1_time,
            self._eligible_setup_count,
            self._precomputed_rejections,
            self._evaluated_expansion_bars,
        ) = _precompute_candidates(
            m5,
            m15,
            spread_points=spread_points,
            all_in_cost_pips=all_in_cost_pips,
            config=self._config,
        )
        self._processed_setup_ids: set[str] = set()
        self._emissions_by_local_date: Counter[date] = Counter()
        self._emitted_signal_count = 0
        self._daily_limit_block_count = 0
        self._reused_setup_block_count = 0

    @property
    def diagnostics(self) -> CompressionExpansionDiagnostics:
        """Return a snapshot; callers cannot mutate strategy accounting."""
        return CompressionExpansionDiagnostics(
            evaluated_expansion_bars=self._evaluated_expansion_bars,
            eligible_setup_count=self._eligible_setup_count,
            eligible_signal_count=len(self._candidates_by_latest_m1_time),
            emitted_signal_count=self._emitted_signal_count,
            daily_limit_block_count=self._daily_limit_block_count,
            reused_setup_block_count=self._reused_setup_block_count,
            rejected_setup_counts=MappingProxyType(dict(self._precomputed_rejections)),
        )

    def __call__(self, latest_m1: pd.DataFrame) -> TradeIntent | None:
        if latest_m1.empty or "time" not in latest_m1:
            raise ValueError("latest M1 input must contain at least one timestamp")
        current_time = pd.Timestamp(latest_m1["time"].iloc[-1])
        if current_time.tzinfo is None:
            raise ValueError("latest M1 timestamp must be timezone-aware")
        current_time = current_time.tz_convert("UTC")
        try:
            self._m1_times.get_loc(current_time)
        except KeyError as error:
            raise ValueError(
                f"M1 timestamp is not present in Strategy 15 data: {current_time}"
            ) from error

        candidate = self._candidates_by_latest_m1_time.get(current_time)
        if candidate is None:
            return None
        if candidate.setup_id in self._processed_setup_ids:
            self._reused_setup_block_count += 1
            return None
        self._processed_setup_ids.add(candidate.setup_id)
        if (
            self._emissions_by_local_date[candidate.local_date]
            >= self._config.maximum_emitted_signals_per_ny_day
        ):
            self._daily_limit_block_count += 1
            return None

        self._emissions_by_local_date[candidate.local_date] += 1
        self._emitted_signal_count += 1
        return TradeIntent(
            direction=candidate.direction,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            maximum_holding_duration=timedelta(
                minutes=self._config.maximum_holding_minutes
            ),
            maximum_candle_gap=timedelta(minutes=1),
            entry_economics=EntryEconomicsConstraints(
                minimum_risk_distance=(
                    self._config.minimum_stop_pips * self._config.pip_size
                ),
                minimum_reward_distance=(
                    self._config.minimum_reward_pips * self._config.pip_size
                ),
                reference_cost_distance=(
                    self._config.stress_reference_cost_pips * self._config.pip_size
                ),
                minimum_cost_adjusted_reward_risk=(
                    self._config.minimum_cost_adjusted_reward_risk
                ),
                maximum_spread_points=self._config.maximum_spread_points,
                maximum_all_in_cost_distance=(
                    self._config.maximum_all_in_cost_pips * self._config.pip_size
                ),
                required_entry_delay_seconds=60.0,
            ),
        )


def _strict_resample(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    bucket = m1["time"].dt.floor(f"{minutes}min")
    grouped = (
        m1.assign(_bucket=bucket)
        .groupby("_bucket", sort=True, as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            tick_volume=("tick_volume", "sum"),
            constituent_count=("time", "size"),
        )
        .rename(columns={"_bucket": "time"})
    )
    complete = grouped.loc[grouped["constituent_count"] == minutes].copy()
    complete["end_time"] = complete["time"] + pd.Timedelta(int(minutes), unit="min")
    return complete.reset_index(drop=True)


def _consecutive_run_lengths(times: pd.Series, minutes: int) -> np.ndarray:
    values = pd.DatetimeIndex(times)
    result = np.ones(len(values), dtype=np.int32)
    if len(values) < 2:
        return result
    consecutive = np.diff(values.asi8) == int(minutes) * 60_000_000_000
    for index in range(1, len(values)):
        result[index] = result[index - 1] + 1 if consecutive[index - 1] else 1
    return result


def _precompute_candidates(
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    *,
    spread_points: float,
    all_in_cost_pips: float,
    config: CompressionExpansionControlledContinuationConfig,
) -> tuple[dict[pd.Timestamp, _EligibleCandidate], int, Counter[str], int]:
    rejections: Counter[str] = Counter()
    if m5.empty or m15.empty:
        return {}, 0, rejections, 0

    ranges = m5["high"] - m5["low"]
    compression = ranges.shift(1).rolling(
        config.compression_bars_m5,
        min_periods=config.compression_bars_m5,
    )
    baseline = ranges.shift(config.compression_bars_m5 + 1).rolling(
        config.baseline_bars_m5,
        min_periods=config.baseline_bars_m5,
    )
    features = pd.DataFrame(
        {
            "compression_median": compression.median(),
            "baseline_q25": baseline.quantile(
                config.compression_baseline_quantile,
                interpolation="linear",
            ),
            "baseline_q75": baseline.quantile(
                config.expansion_min_baseline_quantile,
                interpolation="linear",
            ),
            "baseline_median": baseline.median(),
            "box_high": m5["high"].shift(1).rolling(config.compression_bars_m5).max(),
            "box_low": m5["low"].shift(1).rolling(config.compression_bars_m5).min(),
        }
    )
    m5_runs = _consecutive_run_lengths(m5["time"], 5)
    m15_runs = _consecutive_run_lengths(m15["time"], 15)
    m15_end_ns = pd.DatetimeIndex(m15["end_time"]).asi8
    raw_candidates: list[_EligibleCandidate] = []
    evaluated = 0
    required_m5 = config.baseline_bars_m5 + config.compression_bars_m5 + 1

    for expansion_index in range(len(m5)):
        expansion = m5.iloc[expansion_index]
        local_start = expansion["time"].tz_convert(config.timezone)
        if not _in_expansion_session(local_start, config):
            continue
        if m5_runs[expansion_index] < required_m5:
            rejections["m5_warmup_or_nonconsecutive"] += 1
            continue
        evaluated += 1
        row_features = features.iloc[expansion_index]
        if not _finite_values(row_features):
            rejections["nonfinite_features"] += 1
            continue
        compression_median = float(row_features["compression_median"])
        baseline_q25 = float(row_features["baseline_q25"])
        baseline_q75 = float(row_features["baseline_q75"])
        baseline_median = float(row_features["baseline_median"])
        box_high = float(row_features["box_high"])
        box_low = float(row_features["box_low"])
        width = box_high - box_low
        if compression_median <= 0 or baseline_median <= 0:
            rejections["nonpositive_range"] += 1
            continue
        if compression_median > baseline_q25:
            rejections["compression_threshold"] += 1
            continue
        if width <= 0 or width / config.pip_size > config.maximum_compression_box_pips:
            rejections["compression_box_width"] += 1
            continue

        context_position = int(
            np.searchsorted(m15_end_ns, expansion["time"].value, side="right") - 1
        )
        if (
            context_position < 0
            or m15_runs[context_position] < config.context_required_bars_m15
        ):
            rejections["m15_context_unavailable"] += 1
            continue
        direction = _context_direction(m15, context_position, config)
        if direction is None:
            rejections["m15_context_not_directional"] += 1
            continue
        if not _valid_expansion(
            expansion,
            direction,
            box_high,
            box_low,
            width,
            compression_median,
            baseline_q75,
            baseline_median,
            config,
        ):
            rejections["expansion_threshold"] += 1
            continue

        candidate, reason = _continuation_candidate(
            m5,
            m5_runs,
            expansion_index,
            direction,
            box_high,
            box_low,
            width,
            spread_points,
            all_in_cost_pips,
            config,
        )
        if candidate is None:
            rejections[reason or "continuation_missing"] += 1
            continue
        raw_candidates.append(candidate)

    raw_candidates.sort(key=lambda item: (item.confirmation_time, item.expansion_time))
    by_latest_m1: dict[pd.Timestamp, _EligibleCandidate] = {}
    for candidate in raw_candidates:
        latest_m1_time = candidate.confirmation_time - pd.Timedelta(1, unit="min")
        by_latest_m1.setdefault(latest_m1_time, candidate)
    return by_latest_m1, len(raw_candidates), rejections, evaluated


def _in_expansion_session(
    local_start: pd.Timestamp,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    local_time = local_start.time()
    return (
        local_start.weekday() < 5
        and config.expansion_start_local <= local_time < config.expansion_end_local_exclusive
    )


def _context_direction(
    m15: pd.DataFrame,
    position: int,
    config: CompressionExpansionControlledContinuationConfig,
) -> TradeDirection | None:
    current_start = position - config.context_sma_bars_m15 + 1
    lag_end = position - config.context_slope_lag_bars_m15
    lag_start = lag_end - config.context_sma_bars_m15 + 1
    if lag_start < 0:
        return None
    closes = m15["close"]
    latest_close = float(closes.iloc[position])
    current_sma = float(closes.iloc[current_start : position + 1].mean())
    lagged_sma = float(closes.iloc[lag_start : lag_end + 1].mean())
    if not _finite_values((latest_close, current_sma, lagged_sma)):
        return None
    if latest_close > current_sma > lagged_sma:
        return TradeDirection.BUY
    if latest_close < current_sma < lagged_sma:
        return TradeDirection.SELL
    return None


def _valid_expansion(
    candle: pd.Series,
    direction: TradeDirection,
    box_high: float,
    box_low: float,
    width: float,
    compression_median: float,
    baseline_q75: float,
    baseline_median: float,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])
    candle_range = high - low
    values = (
        open_price,
        high,
        low,
        close,
        candle_range,
        baseline_q75,
        baseline_median,
    )
    if not _finite_values(values) or candle_range <= 0:
        return False
    minimum_range = max(
        config.expansion_min_compression_range_multiple * compression_median,
        baseline_q75,
    )
    if not (
        minimum_range
        <= candle_range
        <= config.expansion_max_baseline_median_multiple * baseline_median
    ):
        return False
    body_fraction = abs(close - open_price) / candle_range
    if body_fraction < config.expansion_min_body_fraction:
        return False

    minimum_clearance = config.breakout_min_clearance_pips * config.pip_size
    maximum_extension = config.breakout_max_extension_box_fraction * width
    if direction is TradeDirection.BUY:
        return (
            close > open_price
            and (high - close) / candle_range <= config.expansion_max_close_edge_fraction
            and minimum_clearance <= close - box_high <= maximum_extension
        )
    return (
        close < open_price
        and (close - low) / candle_range <= config.expansion_max_close_edge_fraction
        and minimum_clearance <= box_low - close <= maximum_extension
    )


def _continuation_candidate(
    m5: pd.DataFrame,
    run_lengths: np.ndarray,
    expansion_index: int,
    direction: TradeDirection,
    box_high: float,
    box_low: float,
    width: float,
    spread_points: float,
    all_in_cost_pips: float,
    config: CompressionExpansionControlledContinuationConfig,
) -> tuple[_EligibleCandidate | None, str | None]:
    final_index = min(
        expansion_index + config.confirmation_max_bars_after_expansion,
        len(m5) - 1,
    )
    if final_index <= expansion_index + 1:
        return None, "continuation_history_unavailable"
    expansion = m5.iloc[expansion_index]
    target = (
        box_high + config.target_box_multiple * width
        if direction is TradeDirection.BUY
        else box_low - config.target_box_multiple * width
    )
    if _target_touched(expansion, direction, target):
        return None, "target_touched_before_entry"

    retest_index: int | None = None
    retest_deadline = min(expansion_index + config.retest_max_bars, final_index - 1)
    for index in range(expansion_index + 1, retest_deadline + 1):
        if run_lengths[index] < index - expansion_index + 1:
            return None, "post_expansion_nonconsecutive"
        candle = m5.iloc[index]
        if _target_touched(candle, direction, target):
            return None, "target_touched_before_entry"
        if _deeply_invalidated(candle, direction, box_high, box_low, width, config):
            return None, "deep_retest_invalidation"
        if _valid_retest(candle, direction, box_high, box_low, width, config):
            retest_index = index
            break
    if retest_index is None:
        return None, "retest_missing"

    for confirmation_index in range(retest_index + 1, final_index + 1):
        if run_lengths[confirmation_index] < confirmation_index - expansion_index + 1:
            return None, "post_expansion_nonconsecutive"
        candle = m5.iloc[confirmation_index]
        local_end = candle["end_time"].tz_convert(config.timezone)
        expansion_local = expansion["time"].tz_convert(config.timezone)
        if (
            local_end.date() != expansion_local.date()
            or local_end.time() > config.confirmation_end_local_inclusive
        ):
            return None, "confirmation_outside_session"
        if _target_touched(candle, direction, target):
            return None, "target_touched_before_entry"
        if _deeply_invalidated(candle, direction, box_high, box_low, width, config):
            return None, "deep_retest_invalidation"
        pullback = m5.iloc[expansion_index + 1 : confirmation_index]
        if not _valid_confirmation(candle, expansion, pullback, direction, config):
            continue

        if direction is TradeDirection.BUY:
            stop = float(m5.iloc[expansion_index + 1 : confirmation_index + 1]["low"].min())
            stop -= config.stop_buffer_pips * config.pip_size
        else:
            stop = float(m5.iloc[expansion_index + 1 : confirmation_index + 1]["high"].max())
            stop += config.stop_buffer_pips * config.pip_size
        signal_close = float(candle["close"])
        if not _signal_economics_pass(signal_close, stop, target, direction, config):
            return None, "signal_economics"
        if (
            spread_points > config.maximum_spread_points
            or all_in_cost_pips > config.maximum_all_in_cost_pips
        ):
            return None, "cost_gate"

        expansion_time = pd.Timestamp(expansion["time"])
        confirmation_time = pd.Timestamp(candle["end_time"])
        setup_id = f"{direction.value}:{expansion_time.isoformat()}"
        return (
            _EligibleCandidate(
                setup_id=setup_id,
                expansion_time=expansion_time,
                confirmation_time=confirmation_time,
                local_date=expansion_local.date(),
                direction=direction,
                stop_loss=stop,
                take_profit=target,
            ),
            None,
        )
    return None, "confirmation_missing"


def _valid_retest(
    candle: pd.Series,
    direction: TradeDirection,
    box_high: float,
    box_low: float,
    width: float,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    high, low, close = (
        float(candle["high"]),
        float(candle["low"]),
        float(candle["close"]),
    )
    if not _finite_values((high, low, close)):
        return False
    if direction is TradeDirection.BUY:
        return (
            box_high - config.retest_inner_box_fraction * width
            <= low
            <= box_high + config.retest_outer_box_fraction * width
            and close >= box_high
        )
    return (
        box_low - config.retest_outer_box_fraction * width
        <= high
        <= box_low + config.retest_inner_box_fraction * width
        and close <= box_low
    )


def _deeply_invalidated(
    candle: pd.Series,
    direction: TradeDirection,
    box_high: float,
    box_low: float,
    width: float,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    close = float(candle["close"])
    if direction is TradeDirection.BUY:
        return close < box_high - config.retest_inner_box_fraction * width
    return close > box_low + config.retest_inner_box_fraction * width


def _valid_confirmation(
    candle: pd.Series,
    expansion: pd.Series,
    pullback: pd.DataFrame,
    direction: TradeDirection,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])
    candle_range = high - low
    if not _finite_values((open_price, high, low, close)) or candle_range <= 0:
        return False
    if abs(close - open_price) / candle_range < config.confirmation_min_body_fraction:
        return False
    clearance = config.confirmation_clearance_pips * config.pip_size
    if direction is TradeDirection.BUY:
        threshold = max(float(expansion["close"]), float(pullback["high"].max()))
        return (
            close > open_price
            and (high - close) / candle_range <= config.confirmation_max_close_edge_fraction
            and close > threshold + clearance
        )
    threshold = min(float(expansion["close"]), float(pullback["low"].min()))
    return (
        close < open_price
        and (close - low) / candle_range <= config.confirmation_max_close_edge_fraction
        and close < threshold - clearance
    )


def _target_touched(
    candle: pd.Series,
    direction: TradeDirection,
    target: float,
) -> bool:
    return (
        float(candle["high"]) >= target
        if direction is TradeDirection.BUY
        else float(candle["low"]) <= target
    )


def _signal_economics_pass(
    signal_close: float,
    stop: float,
    target: float,
    direction: TradeDirection,
    config: CompressionExpansionControlledContinuationConfig,
) -> bool:
    if direction is TradeDirection.BUY:
        risk = signal_close - stop
        reward = target - signal_close
    else:
        risk = stop - signal_close
        reward = signal_close - target
    if not _finite_values((risk, reward)) or risk <= 0 or reward <= 0:
        return False
    risk_pips = risk / config.pip_size
    reward_pips = reward / config.pip_size
    cost = config.stress_reference_cost_pips
    adjusted_reward_risk = (reward_pips - cost) / (risk_pips + cost)
    return (
        risk_pips >= config.minimum_stop_pips
        and reward_pips >= config.minimum_reward_pips
        and adjusted_reward_risk >= config.minimum_cost_adjusted_reward_risk
    )


def _finite_values(values: object) -> bool:
    if isinstance(values, pd.Series):
        array = values.to_numpy(dtype=float)
    else:
        array = np.asarray(tuple(values), dtype=float)
    return bool(np.isfinite(array).all())
