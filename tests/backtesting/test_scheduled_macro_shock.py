from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting.scheduled_macro_shock import (
    ScheduledMacroShockConfig,
    ScheduledMacroShockContinuationStrategy,
)
from mt5_scalping_agent.domain import TradeDirection


def _qualifying_frame(
    local_date: date = date(2023, 7, 10),
    *,
    direction: int = 1,
    shock_pips: float = 10.0,
) -> pd.DataFrame:
    start = pd.Timestamp(f"{local_date.isoformat()} 07:30", tz="America/New_York")
    times = pd.date_range(start, periods=70, freq="min").tz_convert("UTC")
    p0 = 1.1000
    rows: list[dict[str, object]] = []
    for timestamp in times[:60]:
        rows.append(
            {
                "time": timestamp,
                "open": p0,
                "high": p0 + 0.00005,
                "low": p0 - 0.00005,
                "close": p0,
                "tick_volume": 10,
            }
        )
    signed = direction * shock_pips * 0.0001
    previous = p0
    for index, timestamp in enumerate(times[60:65], start=1):
        close = p0 + signed * index / 5
        rows.append(
            {
                "time": timestamp,
                "open": previous,
                "high": max(previous, close) + 0.00005,
                "low": min(previous, close) - 0.00005,
                "close": close,
                "tick_volume": 100,
            }
        )
        previous = close
    fractions = (0.90, 0.86, 0.82, 0.88, 0.98)
    for fraction, timestamp in zip(fractions, times[65:70], strict=True):
        close = p0 + signed * fraction
        rows.append(
            {
                "time": timestamp,
                "open": previous,
                "high": max(previous, close) + 0.00002,
                "low": min(previous, close) - 0.00002,
                "close": close,
                "tick_volume": 50,
            }
        )
        previous = close
    return pd.DataFrame(rows)


def _strategy(**kwargs: float) -> ScheduledMacroShockContinuationStrategy:
    return ScheduledMacroShockContinuationStrategy(
        spread_points=kwargs.pop("spread_points", 4.0),
        all_in_cost_pips=kwargs.pop("all_in_cost_pips", 1.0),
        config=ScheduledMacroShockConfig(**kwargs),
    )


def test_qualifying_buy_emits_exact_frozen_plan() -> None:
    frame = _qualifying_frame()
    intent = _strategy()(frame)

    assert intent is not None
    assert intent.direction is TradeDirection.BUY
    assert intent.stop_loss == pytest.approx(1.10045)
    assert intent.take_profit == pytest.approx(1.1021725)
    assert intent.target_reward_risk_multiple == 2.25
    assert intent.maximum_holding_duration.total_seconds() == 80 * 60
    assert intent.entry_economics is not None
    assert intent.entry_economics.required_entry_delay_seconds == 60
    assert intent.entry_economics.reference_cost_distance == pytest.approx(0.00019)


def test_qualifying_sell_is_exact_mirror() -> None:
    intent = _strategy()(_qualifying_frame(direction=-1))

    assert intent is not None
    assert intent.direction is TradeDirection.SELL
    assert intent.stop_loss == pytest.approx(1.09955)
    assert intent.take_profit == pytest.approx(1.0978275)


@pytest.mark.parametrize(
    ("local_date", "expected_utc"),
    [
        (date(2023, 1, 9), "2023-01-09 13:39:00+00:00"),
        (date(2023, 7, 10), "2023-07-10 12:39:00+00:00"),
    ],
)
def test_new_york_clock_is_dst_aware(local_date: date, expected_utc: str) -> None:
    frame = _qualifying_frame(local_date)

    assert str(frame["time"].iloc[-1]) == expected_utc
    assert _strategy()(frame) is not None


def test_non_signal_minute_is_ignored_without_evaluation() -> None:
    frame = _qualifying_frame().iloc[:-1]
    strategy = _strategy()

    assert strategy(frame) is None
    assert strategy.diagnostics.evaluated_event_dates == 0


def test_missing_required_minute_is_rejected() -> None:
    frame = _qualifying_frame().drop(index=20).reset_index(drop=True)
    duplicate = frame.iloc[[-1]].copy()
    frame = pd.concat([frame, duplicate], ignore_index=True)
    strategy = _strategy()

    assert strategy(frame) is None
    assert strategy.diagnostics.rejected_setup_counts == {
        "nonconsecutive_required_window": 1
    }


def test_weekend_is_rejected() -> None:
    strategy = _strategy()

    assert strategy(_qualifying_frame(date(2023, 7, 8))) is None
    assert strategy.diagnostics.rejected_setup_counts == {"weekend": 1}


def test_small_shock_is_rejected() -> None:
    strategy = _strategy()

    assert strategy(_qualifying_frame(shock_pips=6.0)) is None
    assert strategy.diagnostics.rejected_setup_counts == {"shock_displacement": 1}


def test_failed_final_retention_is_rejected() -> None:
    frame = _qualifying_frame()
    index = 69
    frame.loc[index, "close"] = 1.10060
    frame.loc[index, "low"] = 1.10060
    strategy = _strategy()

    assert strategy(frame) is None
    assert strategy.diagnostics.rejected_setup_counts == {"final_retention": 1}


def test_failed_reacceleration_is_rejected() -> None:
    frame = _qualifying_frame()
    frame.loc[69, "close"] = 1.10085
    frame.loc[69, "low"] = min(frame.loc[69, "low"], 1.10083)
    strategy = _strategy(minimum_final_retained_fraction=0.80)

    assert strategy(frame) is None
    assert strategy.diagnostics.rejected_setup_counts == {"reacceleration": 1}


def test_excessive_retracement_is_rejected_using_extreme() -> None:
    frame = _qualifying_frame()
    frame.loc[67, "low"] = 1.10055
    strategy = _strategy()

    assert strategy(frame) is None
    assert strategy.diagnostics.rejected_setup_counts == {
        "stabilization_retracement": 1
    }


def test_signal_level_stop_floor_is_enforced() -> None:
    frame = _qualifying_frame()
    frame.loc[69, "close"] = 1.10090
    strategy = _strategy(minimum_stop_pips=6.0)

    assert strategy(frame) is None
    assert strategy.diagnostics.rejected_setup_counts == {"minimum_stop": 1}


def test_cost_gates_are_frozen() -> None:
    assert _strategy(spread_points=10.01)(_qualifying_frame()) is None
    assert _strategy(all_in_cost_pips=1.91)(_qualifying_frame()) is None


def test_emitted_date_cannot_be_refunded_or_reused() -> None:
    frame = _qualifying_frame()
    strategy = _strategy()

    assert strategy(frame) is not None
    assert strategy(frame) is None
    diagnostics = strategy.diagnostics
    assert diagnostics.emitted_signal_count == 1
    assert diagnostics.daily_limit_block_count == 1
    assert diagnostics.rejected_setup_counts["daily_limit"] == 1


def test_diagnostics_snapshot_is_immutable() -> None:
    strategy = _strategy()
    assert strategy(_qualifying_frame()) is not None
    snapshot = strategy.diagnostics

    with pytest.raises(FrozenInstanceError):
        snapshot.emitted_signal_count = 2  # type: ignore[misc]


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum stop"):
        ScheduledMacroShockConfig(minimum_stop_pips=16, maximum_stop_pips=15)
    with pytest.raises(ValueError, match="cannot exceed one"):
        ScheduledMacroShockConfig(minimum_final_retained_fraction=1.1)