from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from mt5_scalping_agent.backtesting.compression_expansion_continuation import (
    CompressionExpansionControlledContinuationConfig,
    CompressionExpansionControlledContinuationStrategy,
)
from mt5_scalping_agent.domain import TradeDirection


PIP = 0.0001


def _designed_m5(
    *,
    direction: TradeDirection = TradeDirection.BUY,
    expansion_start: str = "2025-01-06T13:00:00Z",
    weak_expansion: bool = False,
    deep_retest: bool = False,
    target_touch: bool = False,
    confirmation_at_clearance_boundary: bool = False,
) -> tuple[pd.DataFrame, dict[str, object]]:
    expansion_time = pd.Timestamp(expansion_start)
    expansion_index = 84
    first_time = expansion_time - pd.Timedelta(5 * expansion_index, unit="min")
    times = pd.date_range(first_time, periods=expansion_index + 8, freq="5min")
    rows: list[dict[str, object]] = []

    for index, timestamp in enumerate(times):
        center = 1.1000 + index * 0.00005
        rows.append(
            {
                "time": timestamp,
                "open": center - 0.00002,
                "high": center + 0.00020,
                "low": center - 0.00020,
                "close": center + 0.00002,
                "tick_volume": 5,
            }
        )

    box_low, box_high = 1.1035, 1.1045
    centers = np.linspace(box_low + 0.00005, box_high - 0.00005, 12)
    for offset, center in enumerate(centers):
        index = expansion_index - 12 + offset
        rows[index].update(
            open=center - 0.00002,
            high=center + 0.00005,
            low=center - 0.00005,
            close=center + 0.00002,
        )

    expansion_close = box_high + (0.00005 if weak_expansion else 0.00025)
    rows[expansion_index].update(
        open=box_high - 0.00010,
        high=box_high + 0.00030,
        low=box_high - 0.00015,
        close=expansion_close,
    )
    rows[expansion_index + 1].update(
        open=box_high + 0.00025,
        high=box_high + 0.00030,
        low=box_high + 0.00010,
        close=(box_high - 0.00030 if deep_retest else box_high + 0.00012),
    )
    confirmation_close = (
        box_high + 0.00032
        if confirmation_at_clearance_boundary
        else box_high + 0.00048
    )
    target = box_high + 1.5 * (box_high - box_low)
    rows[expansion_index + 2].update(
        open=box_high + 0.00012,
        high=(target if target_touch else box_high + 0.00050),
        low=box_high + 0.00010,
        close=confirmation_close,
    )

    m5 = pd.DataFrame(rows)
    if direction is TradeDirection.SELL:
        mirror = 2.2050
        original_high = m5["high"].copy()
        original_low = m5["low"].copy()
        m5["open"] = mirror - m5["open"]
        m5["high"] = mirror - original_low
        m5["low"] = mirror - original_high
        m5["close"] = mirror - m5["close"]

    return m5, {
        "expansion_index": expansion_index,
        "confirmation_time": pd.Timestamp(times[expansion_index + 2]) + pd.Timedelta(5, unit="min"),
        "box_high": box_high if direction is TradeDirection.BUY else 2.2050 - box_low,
        "box_low": box_low if direction is TradeDirection.BUY else 2.2050 - box_high,
    }


def _expand_m5_to_m1(m5: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for candle in m5.itertuples(index=False):
        nodes = np.linspace(float(candle.open), float(candle.close), 6)
        for minute in range(5):
            open_price, close = float(nodes[minute]), float(nodes[minute + 1])
            high, low = max(open_price, close), min(open_price, close)
            if minute == 0:
                high = max(high, float(candle.high))
                low = min(low, float(candle.low))
            rows.append(
                {
                    "time": pd.Timestamp(candle.time) + pd.Timedelta(minute, unit="min"),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "tick_volume": 1,
                }
            )
    return pd.DataFrame(rows)


def _fixture(**kwargs: object) -> tuple[pd.DataFrame, dict[str, object]]:
    m5, metadata = _designed_m5(**kwargs)
    return _expand_m5_to_m1(m5), metadata


def _latest_at_signal(m1: pd.DataFrame, metadata: dict[str, object]) -> pd.DataFrame:
    timestamp = pd.Timestamp(metadata["confirmation_time"]) - pd.Timedelta(1, unit="min")
    return m1.loc[m1["time"] == timestamp]


def test_emits_exact_frozen_buy_intent_and_diagnostics() -> None:
    m1, metadata = _fixture()
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    intent = strategy(_latest_at_signal(m1, metadata))

    assert intent is not None
    assert intent.direction is TradeDirection.BUY
    assert intent.stop_loss == pytest.approx(1.10455)
    assert intent.take_profit == pytest.approx(1.1060)
    assert intent.maximum_holding_duration == timedelta(minutes=120)
    assert intent.maximum_candle_gap == timedelta(minutes=1)
    assert intent.entry_economics is not None
    assert intent.entry_economics.minimum_risk_distance == pytest.approx(4 * PIP)
    assert intent.entry_economics.minimum_reward_distance == pytest.approx(6 * PIP)
    assert intent.entry_economics.reference_cost_distance == pytest.approx(PIP)
    assert intent.entry_economics.maximum_spread_points == 4
    assert intent.entry_economics.required_entry_delay_seconds == 60
    assert strategy.diagnostics.eligible_setup_count >= 1
    assert strategy.diagnostics.eligible_signal_count >= 1
    assert strategy.diagnostics.emitted_signal_count == 1

    assert strategy(_latest_at_signal(m1, metadata)) is None
    assert strategy.diagnostics.reused_setup_block_count == 1


def test_sell_is_an_exact_mirror_of_buy() -> None:
    m1, metadata = _fixture(direction=TradeDirection.SELL)
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    intent = strategy(_latest_at_signal(m1, metadata))

    assert intent is not None
    assert intent.direction is TradeDirection.SELL
    assert intent.stop_loss == pytest.approx(1.10045)
    assert intent.take_profit == pytest.approx(1.0990)
    assert intent.take_profit < intent.stop_loss


@pytest.mark.parametrize(
    "expansion_start",
    ["2025-01-06T13:00:00Z", "2025-07-07T12:00:00Z"],
)
def test_session_uses_new_york_civil_time_across_dst(expansion_start: str) -> None:
    m1, metadata = _fixture(expansion_start=expansion_start)
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    assert strategy(_latest_at_signal(m1, metadata)) is not None


@pytest.mark.parametrize(
    "expansion_start",
    ["2025-01-06T12:30:00Z", "2025-01-11T13:00:00Z"],
)
def test_rejects_off_session_and_weekend_expansions(expansion_start: str) -> None:
    m1, metadata = _fixture(expansion_start=expansion_start)
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    assert strategy(_latest_at_signal(m1, metadata)) is None


def test_expansion_at_exact_new_york_1130_cutoff_is_excluded() -> None:
    m1, metadata = _fixture(expansion_start="2025-01-06T16:30:00Z")
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    assert strategy(_latest_at_signal(m1, metadata)) is None


def test_incomplete_constituent_breaks_the_required_causal_sequence() -> None:
    m1, metadata = _fixture()
    expansion_index = int(metadata["expansion_index"])
    missing = m1["time"].iloc[(expansion_index - 6) * 5 + 2]
    incomplete = m1.loc[m1["time"] != missing].reset_index(drop=True)
    strategy = CompressionExpansionControlledContinuationStrategy(incomplete)

    assert strategy(_latest_at_signal(incomplete, metadata)) is None
    assert strategy.diagnostics.rejected_setup_counts["m5_warmup_or_nonconsecutive"] > 0


def test_incomplete_m15_context_blocks_signal_when_required_m5_is_complete() -> None:
    m1, metadata = _fixture()
    # This missing 07:00 UTC constituent is inside the six-hour M15 context but
    # before the five-hour M5 baseline/compression sequence beginning at 08:00.
    missing = m1["time"].iloc[12 * 5 + 2]
    incomplete = m1.loc[m1["time"] != missing].reset_index(drop=True)
    strategy = CompressionExpansionControlledContinuationStrategy(incomplete)

    assert strategy(_latest_at_signal(incomplete, metadata)) is None
    assert strategy.diagnostics.rejected_setup_counts["m15_context_unavailable"] > 0


def test_future_prices_do_not_change_the_signal() -> None:
    m1, metadata = _fixture()
    signal_start = pd.Timestamp(metadata["confirmation_time"]) - pd.Timedelta(1, unit="min")
    prefix = m1.loc[m1["time"] <= signal_start].reset_index(drop=True)
    changed = m1.copy()
    changed.loc[changed["time"] > signal_start, ["open", "high", "low", "close"]] += 0.25

    prefix_intent = CompressionExpansionControlledContinuationStrategy(prefix)(
        _latest_at_signal(prefix, metadata)
    )
    full_intent = CompressionExpansionControlledContinuationStrategy(changed)(
        _latest_at_signal(changed, metadata)
    )

    assert prefix_intent == full_intent
    assert prefix_intent is not None


@pytest.mark.parametrize(
    ("fixture_kwargs", "reason"),
    [
        ({"weak_expansion": True}, "expansion_threshold"),
        ({"deep_retest": True}, "deep_retest_invalidation"),
        ({"target_touch": True}, "target_touched_before_entry"),
        ({"confirmation_at_clearance_boundary": True}, "confirmation_missing"),
    ],
)
def test_exact_pattern_rejections(
    fixture_kwargs: dict[str, bool],
    reason: str,
) -> None:
    m1, metadata = _fixture(**fixture_kwargs)
    strategy = CompressionExpansionControlledContinuationStrategy(m1)

    assert strategy(_latest_at_signal(m1, metadata)) is None
    assert strategy.diagnostics.rejected_setup_counts[reason] > 0


@pytest.mark.parametrize(
    ("spread_points", "all_in_cost_pips"),
    [(4.0001, 0.7), (2.0, 1.0001)],
)
def test_cost_gate_rejects_values_above_frozen_stress_envelope(
    spread_points: float,
    all_in_cost_pips: float,
) -> None:
    m1, metadata = _fixture()
    strategy = CompressionExpansionControlledContinuationStrategy(
        m1,
        spread_points=spread_points,
        all_in_cost_pips=all_in_cost_pips,
    )

    assert strategy(_latest_at_signal(m1, metadata)) is None
    assert strategy.diagnostics.rejected_setup_counts["cost_gate"] > 0


def test_stress_cost_boundary_preserves_the_signal() -> None:
    m1, metadata = _fixture()
    strategy = CompressionExpansionControlledContinuationStrategy(
        m1,
        spread_points=4.0,
        all_in_cost_pips=1.0,
    )

    assert strategy(_latest_at_signal(m1, metadata)) is not None


def test_maximum_two_emissions_per_new_york_date_and_setup_deduplication() -> None:
    m1, metadata = _fixture()
    strategy = CompressionExpansionControlledContinuationStrategy(m1)
    candidate = next(iter(strategy._candidates_by_latest_m1_time.values()))
    base_time = next(iter(strategy._candidates_by_latest_m1_time))
    times = [base_time + pd.Timedelta(offset, unit="min") for offset in range(3)]
    strategy._candidates_by_latest_m1_time = {
        timestamp: replace(candidate, setup_id=f"setup-{index}")
        for index, timestamp in enumerate(times)
    }

    first = strategy(m1.loc[m1["time"] == times[0]])
    assert first is not None
    assert strategy(m1.loc[m1["time"] == times[0]]) is None
    second = strategy(m1.loc[m1["time"] == times[1]])
    third = strategy(m1.loc[m1["time"] == times[2]])

    assert second is not None
    assert third is None
    assert strategy.diagnostics.emitted_signal_count == 2
    assert strategy.diagnostics.daily_limit_block_count == 1
    assert strategy.diagnostics.reused_setup_block_count == 1


def test_daily_emission_limit_resets_on_next_new_york_date() -> None:
    first_m1, _ = _fixture(expansion_start="2025-01-06T13:00:00Z")
    second_m1, _ = _fixture(expansion_start="2025-01-07T13:00:00Z")
    combined = pd.concat([first_m1, second_m1], ignore_index=True)
    strategy = CompressionExpansionControlledContinuationStrategy(combined)
    candidates = sorted(
        strategy._candidates_by_latest_m1_time.items(),
        key=lambda item: item[0],
    )
    first_time, first_candidate = candidates[0]
    second_date_time, second_date_candidate = candidates[-1]
    additional_first_date_time = first_time + pd.Timedelta(1, unit="min")
    strategy._candidates_by_latest_m1_time = {
        first_time: replace(first_candidate, setup_id="first-date-1"),
        additional_first_date_time: replace(first_candidate, setup_id="first-date-2"),
        second_date_time: replace(second_date_candidate, setup_id="second-date-1"),
    }

    assert strategy(combined.loc[combined["time"] == first_time]) is not None
    assert strategy(combined.loc[combined["time"] == additional_first_date_time]) is not None
    assert strategy(combined.loc[combined["time"] == second_date_time]) is not None
    assert strategy.diagnostics.emitted_signal_count == 3
    assert strategy.diagnostics.daily_limit_block_count == 0


def test_externally_rejected_intent_still_consumes_daily_emission() -> None:
    m1, _ = _fixture()
    strategy = CompressionExpansionControlledContinuationStrategy(m1)
    candidate = next(iter(strategy._candidates_by_latest_m1_time.values()))
    base_time = next(iter(strategy._candidates_by_latest_m1_time))
    times = [base_time + pd.Timedelta(offset, unit="min") for offset in range(3)]
    strategy._candidates_by_latest_m1_time = {
        timestamp: replace(candidate, setup_id=f"external-rejection-{index}")
        for index, timestamp in enumerate(times)
    }

    rejected_elsewhere = strategy(m1.loc[m1["time"] == times[0]])
    assert rejected_elsewhere is not None
    # The strategy has no acceptance callback. An engine/risk rejection cannot
    # refund this emitted signal, which is the prospectively frozen behavior.
    assert strategy.diagnostics.emitted_signal_count == 1
    assert strategy(m1.loc[m1["time"] == times[1]]) is not None
    assert strategy(m1.loc[m1["time"] == times[2]]) is None
    assert strategy.diagnostics.emitted_signal_count == 2
    assert strategy.diagnostics.daily_limit_block_count == 1


def test_diagnostics_rejection_mapping_is_read_only() -> None:
    m1, _ = _fixture()
    diagnostics = CompressionExpansionControlledContinuationStrategy(m1).diagnostics

    with pytest.raises(TypeError):
        diagnostics.rejected_setup_counts["tamper"] = 1  # type: ignore[index]


def test_rejects_invalid_frozen_configuration() -> None:
    with pytest.raises(ValueError, match="confirmation deadline"):
        CompressionExpansionControlledContinuationConfig(
            retest_max_bars=4,
            confirmation_max_bars_after_expansion=4,
        )
