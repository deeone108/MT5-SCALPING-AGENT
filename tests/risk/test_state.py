from datetime import UTC, datetime, timedelta

import pytest

from mt5_scalping_agent.risk import RiskStateError, RiskStateTracker


def test_tracker_propagates_trade_counts_exposure_pnl_and_loss_streak() -> None:
    tracker = RiskStateTracker(10_000)
    opened_at = datetime(2026, 1, 5, 12, 5, tzinfo=UTC)

    tracker.record_trade_open(opened_at, "EURUSD", 0.5)
    opened = tracker.snapshot(opened_at, symbol="EURUSD")

    assert opened.open_position_count == 1
    assert opened.current_exposure_lots == pytest.approx(0.5)
    assert opened.symbol_exposure_lots == pytest.approx(0.5)
    assert opened.trades_current_hour == 1
    assert opened.trades_current_day == 1

    tracker.record_trade_close(opened_at + timedelta(minutes=2), "EURUSD", 0.5, -100.0)
    losing = tracker.snapshot(opened_at + timedelta(minutes=2), symbol="EURUSD")

    assert losing.balance == pytest.approx(9_900)
    assert losing.daily_realized_pnl == pytest.approx(-100)
    assert losing.weekly_realized_pnl == pytest.approx(-100)
    assert losing.daily_starting_equity == pytest.approx(10_000)
    assert losing.weekly_starting_equity == pytest.approx(10_000)
    assert losing.consecutive_losses == 1
    assert losing.open_position_count == 0
    assert losing.current_exposure_lots == 0

    tracker.record_trade_open(opened_at + timedelta(minutes=10), "EURUSD", 0.25)
    tracker.record_trade_close(opened_at + timedelta(minutes=11), "EURUSD", 0.25, 50.0)
    winning = tracker.snapshot(opened_at + timedelta(minutes=11), symbol="EURUSD")

    assert winning.daily_realized_pnl == pytest.approx(-50)
    assert winning.consecutive_losses == 0
    assert winning.trades_current_hour == 2
    assert winning.trades_current_day == 2


def test_tracker_resets_daily_streak_and_preserves_weekly_loss() -> None:
    tracker = RiskStateTracker(10_000)
    monday = datetime(2026, 1, 5, 23, 58, tzinfo=UTC)
    tracker.record_trade_open(monday, "EURUSD", 0.1)
    tracker.record_trade_close(monday, "EURUSD", 0.1, -25.0)

    tuesday = tracker.snapshot(monday + timedelta(minutes=3), symbol="EURUSD")

    assert tuesday.consecutive_losses == 0
    assert tuesday.daily_realized_pnl == 0
    assert tuesday.daily_starting_equity == pytest.approx(9_975)
    assert tuesday.weekly_realized_pnl == pytest.approx(-25)
    assert tuesday.weekly_starting_equity == pytest.approx(10_000)


def test_tracker_observes_mark_to_market_peak_and_drawdown_state() -> None:
    tracker = RiskStateTracker(10_000)
    timestamp = datetime(2026, 1, 5, 12, tzinfo=UTC)

    peak = tracker.snapshot(timestamp, symbol="EURUSD", mark_to_market_pnl=200)
    drawdown = tracker.snapshot(
        timestamp + timedelta(minutes=1), symbol="EURUSD", mark_to_market_pnl=-300
    )

    assert peak.equity == pytest.approx(10_200)
    assert peak.peak_equity == pytest.approx(10_200)
    assert drawdown.equity == pytest.approx(9_700)
    assert drawdown.peak_equity == pytest.approx(10_200)


def test_tracker_rejects_inconsistent_close_and_naive_time() -> None:
    tracker = RiskStateTracker(10_000)
    timestamp = datetime(2026, 1, 5, 12, tzinfo=UTC)

    with pytest.raises(RiskStateError, match="not tracked"):
        tracker.record_trade_close(timestamp, "EURUSD", 0.1, -10)
    with pytest.raises(ValueError, match="timezone-aware"):
        tracker.snapshot(datetime(2026, 1, 5, 12), symbol="EURUSD")

def test_tracker_can_preserve_loss_streak_across_days_when_policy_disables_reset() -> None:
    tracker = RiskStateTracker(
        10_000,
        reset_consecutive_losses_each_utc_day=False,
    )
    monday = datetime(2026, 1, 5, 23, 58, tzinfo=UTC)
    tracker.record_trade_open(monday, "EURUSD", 0.1)
    tracker.record_trade_close(monday, "EURUSD", 0.1, -25.0)

    tuesday = tracker.snapshot(monday + timedelta(minutes=3), symbol="EURUSD")

    assert tuesday.consecutive_losses == 1