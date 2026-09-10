"""Frozen Phase 22A causal anchor, feature, and inference primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

LOOKBACKS = (1, 5, 15)
HORIZONS = (1, 5, 15, 30, 60)
FRESH_NS = 2_000_000_000


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def temporal_partition(year: int) -> str:
    if 2019 <= year <= 2021:
        return "DISCOVERY"
    if year == 2022:
        return "CONFIRMATION"
    if year == 2023:
        return "INTERNAL_HOLDOUT"
    raise ValueError("Phase 22A forbids years outside 2019-2023")


def build_anchor_table(ticks: pd.DataFrame, pair: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Build causal 10-second anchors from a context-bearing tick frame."""
    times = ticks["timestamp_utc_ns"].to_numpy(dtype="int64")
    bid = ticks["bid"].to_numpy(dtype="float64")
    ask = ticks["ask"].to_numpy(dtype="float64")
    if len(times) == 0 or np.any(np.diff(times) < 0):
        raise ValueError("ticks must be nonempty and chronological")
    start_ns, end_ns = int(start.value), int(end.value)
    anchors = np.arange(start_ns, end_ns, 10_000_000_000, dtype="int64")
    current_pos = np.searchsorted(times, anchors, side="right") - 1
    valid_pos = current_pos >= 0
    safe_pos = np.maximum(current_pos, 0)
    quote_age = anchors - times[safe_pos]
    eligible = valid_pos & (quote_age >= 0) & (quote_age <= FRESH_NS)
    anchors = anchors[eligible]
    current_pos = current_pos[eligible]
    quote_age = quote_age[eligible]
    current_mid = (bid[current_pos] + ask[current_pos]) / 2
    current_spread = ask[current_pos] - bid[current_pos]
    out = pd.DataFrame(
        {
            "anchor_utc_ns": anchors,
            "quote_utc_ns": times[current_pos],
            "quote_age_ns": quote_age,
            "bid": bid[current_pos],
            "ask": ask[current_pos],
            "mid": current_mid,
            "spread_price": current_spread,
            "spread_pips": current_spread / pip_size(pair),
        }
    )

    mid = (bid + ask) / 2
    delta = np.diff(mid, prepend=mid[0])
    up_prefix = np.concatenate(([0], np.cumsum(delta > 0)))
    down_prefix = np.concatenate(([0], np.cumsum(delta < 0)))
    abs_prefix = np.concatenate(([0.0], np.cumsum(np.abs(delta))))
    pos_prefix = np.concatenate(([0.0], np.cumsum(np.maximum(delta, 0))))
    neg_prefix = np.concatenate(([0.0], np.cumsum(np.maximum(-delta, 0))))

    for window in LOOKBACKS:
        window_ns = window * 1_000_000_000
        left = np.searchsorted(times, anchors - window_ns, side="right")
        right = np.searchsorted(times, anchors, side="right")
        up = up_prefix[right] - up_prefix[left]
        down = down_prefix[right] - down_prefix[left]
        changing = up + down
        out[f"qdi_{window}s"] = np.divide(
            up - down, changing, out=np.full(len(out), np.nan), where=changing > 0
        )
        out[f"changing_ticks_{window}s"] = changing
        out[f"total_ticks_{window}s"] = right - left
        out[f"up_magnitude_{window}s"] = pos_prefix[right] - pos_prefix[left]
        out[f"down_magnitude_{window}s"] = neg_prefix[right] - neg_prefix[left]

        past_target = anchors - window_ns
        past_pos = np.searchsorted(times, past_target, side="right") - 1
        safe = np.maximum(past_pos, 0)
        fresh = (past_pos >= 0) & (past_target - times[safe] >= 0) & (past_target - times[safe] <= FRESH_NS)
        impulse = np.full(len(out), np.nan)
        impulse[fresh] = (current_mid[fresh] - mid[safe[fresh]]) / pip_size(pair)
        out[f"impulse_{window}s_pips"] = impulse
        out[f"impulse_{window}s_spread"] = np.divide(
            impulse, out["spread_pips"], out=np.full(len(out), np.nan), where=out["spread_pips"] > 0
        )

        baseline_left = np.searchsorted(times, anchors - window_ns - 60_000_000_000, side="left")
        baseline_right = np.searchsorted(times, anchors - window_ns, side="left")
        baseline_ticks = baseline_right - baseline_left
        expected = baseline_ticks * window / 60
        out[f"activity_{window}s"] = np.divide(
            right - left, expected, out=np.full(len(out), np.nan), where=expected > 0
        )
        recent_abs = abs_prefix[right] - abs_prefix[left]
        baseline_abs = abs_prefix[baseline_right] - abs_prefix[baseline_left]
        expected_abs = baseline_abs * window / 60
        out[f"volatility_{window}s"] = np.divide(
            recent_abs, expected_abs, out=np.full(len(out), np.nan), where=expected_abs > 0
        )

    out["spread_dislocation"] = (
        out["spread_pips"]
        / out["spread_pips"].shift(1).rolling(6, min_periods=4).median()
    )

    for horizon in HORIZONS:
        target = anchors + horizon * 1_000_000_000
        future_pos = np.searchsorted(times, target, side="right") - 1
        safe = np.maximum(future_pos, 0)
        age = target - times[safe]
        valid = (future_pos >= 0) & (times[safe] > anchors) & (age >= 0) & (age <= FRESH_NS)
        future_mid = np.full(len(out), np.nan)
        future_spread = np.full(len(out), np.nan)
        future_mid[valid] = mid[safe[valid]]
        future_spread[valid] = (ask[safe[valid]] - bid[safe[valid]]) / pip_size(pair)
        change = (future_mid - current_mid) / pip_size(pair)
        out[f"future_age_{horizon}s_ns"] = np.where(valid, age, np.nan)
        out[f"future_change_{horizon}s_pips"] = change
        out[f"future_change_{horizon}s_spread"] = np.divide(
            change, out["spread_pips"], out=np.full(len(out), np.nan), where=out["spread_pips"] > 0
        )
        out[f"future_abs_{horizon}s_spread"] = np.abs(out[f"future_change_{horizon}s_spread"])
        out[f"future_spread_normalization_{horizon}s"] = np.divide(
            future_spread, out["spread_pips"], out=np.full(len(out), np.nan), where=out["spread_pips"] > 0
        ) - 1
        for threshold in (0.5, 1.0, 2.0):
            out[f"future_abs_ge_{threshold:g}_{horizon}s"] = (
                out[f"future_abs_{horizon}s_spread"] >= threshold
            ).where(valid)
    out["pair"] = pair
    out["year"] = pd.to_datetime(out.anchor_utc_ns, unit="ns", utc=True).dt.year
    out["month"] = pd.to_datetime(out.anchor_utc_ns, unit="ns", utc=True).dt.month
    out["day"] = pd.to_datetime(out.anchor_utc_ns, unit="ns", utc=True).dt.strftime("%Y-%m-%d")
    return out


def quantile_boundaries(values: np.ndarray) -> list[float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        raise ValueError("cannot freeze quantiles without discovery observations")
    return [float(x) for x in np.quantile(finite, [0.2, 0.4, 0.6, 0.8])]


def apply_frozen_bins(values: np.ndarray, boundaries: list[float]) -> np.ndarray:
    if len(boundaries) != 4:
        raise ValueError("four frozen quintile boundaries required")
    return np.searchsorted(np.asarray(boundaries), values, side="right") + 1


def block_bootstrap(daily: np.ndarray, *, resamples: int = 10_000, seed: int = 22_001) -> dict[str, float]:
    daily = daily[np.isfinite(daily)]
    if len(daily) < 2:
        raise ValueError("at least two trading-day blocks required")
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for offset in range(0, resamples, 500):
        size = min(500, resamples - offset)
        indices = rng.integers(0, len(daily), size=(size, len(daily)))
        means[offset : offset + size] = daily[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "mean": float(daily.mean()),
        "median_daily": float(np.median(daily)),
        "ci_low": float(low),
        "ci_high": float(high),
        "fraction_positive": float((daily > 0).mean()),
        "fraction_negative": float((daily < 0).mean()),
        "p_two_sided": float(min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))),
    }


def benjamini_hochberg(p_values: dict[str, float], q: float = 0.05) -> dict[str, bool]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    cutoff = -1
    total = len(ordered)
    for index, (_, value) in enumerate(ordered, 1):
        if value <= q * index / total:
            cutoff = index
    accepted = {name: False for name in p_values}
    for name, _ in ordered[:max(cutoff, 0)]:
        accepted[name] = True
    return accepted


def assert_dataset_root(actual: str, expected: str) -> None:
    if actual != expected:
        raise ValueError(f"dataset root mismatch: expected {expected}, got {actual}")