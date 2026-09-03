import pandas as pd
import pytest

from mt5_scalping_agent.data.tick_analysis import TickAnalysisError, analyze_tick_spreads


def _write_ticks(path, rows) -> None:  # type: ignore[no-untyped-def]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_analyze_tick_spreads_separates_fresh_and_stale_records(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [
        {"observed_at": "2025-01-01T08:00:01Z", "tick_time": "2025-01-01T08:00:00Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10},
        {"observed_at": "2025-01-01T08:00:10Z", "tick_time": "2025-01-01T08:00:00Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1002, "spread_points": 20},
    ])

    result = analyze_tick_spreads(path, maximum_tick_age_seconds=5)

    assert result["fresh_record_count"] == 1
    assert result["stale_record_count"] == 1
    assert result["spread_points_fresh"]["median"] == 10.0
    assert result["spread_points_all"]["p95"] == pytest.approx(19.5)
    assert result["fresh_session_spreads"][0]["session"] == "london"
    assert result["recommended_conservative_spread_points"] == 10.0


def test_analyze_tick_spreads_uses_highest_normal_session_p95(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [
        {"observed_at": "2025-01-01T08:00:01Z", "tick_time": "2025-01-01T08:00:00Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10},
        {"observed_at": "2025-01-01T13:00:01Z", "tick_time": "2025-01-01T13:00:00Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1003, "spread_points": 30},
    ])

    assert analyze_tick_spreads(path)["recommended_conservative_spread_points"] == 30.0


def test_analyze_tick_spreads_rejects_negative_tick_age(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [{"observed_at": "2025-01-01T00:00:00Z", "tick_time": "2025-01-01T00:00:01Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10}])

    with pytest.raises(TickAnalysisError, match="negative"):
        analyze_tick_spreads(path)


def test_analyze_tick_spreads_applies_explicit_broker_offset(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [{"observed_at": "2025-01-01T07:00:01Z", "tick_time": "2025-01-01T10:00:00Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10}])

    result = analyze_tick_spreads(path, broker_time_offset_hours=3)

    assert result["fresh_record_count"] == 1
    assert result["broker_time_offset_hours"] == 3

def test_analyze_tick_spreads_allows_explicit_small_clock_skew(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [{"observed_at": "2025-01-01T07:00:00Z", "tick_time": "2025-01-01T07:00:00.500Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10}])

    result = analyze_tick_spreads(path, maximum_clock_skew_seconds=1)

    assert result["fresh_record_count"] == 1

def test_analyze_tick_spreads_accepts_mixed_timestamp_precision(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    _write_ticks(path, [
        {"observed_at": "2025-01-01T07:00:01.100Z", "tick_time": "2025-01-01T07:00:01Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10},
        {"observed_at": "2025-01-01T07:00:02Z", "tick_time": "2025-01-01T07:00:01.500Z", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10},
    ])

    assert analyze_tick_spreads(path)["fresh_record_count"] == 2