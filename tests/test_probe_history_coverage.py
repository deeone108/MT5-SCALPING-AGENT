from datetime import UTC, datetime

import pytest

from scripts.probe_history_coverage import sample_day


def test_sample_day_is_utc_weekday() -> None:
    assert sample_day(2026) == datetime(2026, 7, 1, tzinfo=UTC)
    assert sample_day(2028) == datetime(2028, 7, 3, tzinfo=UTC)


def test_sample_day_rejects_no_input_only_through_parser() -> None:
    assert sample_day(2027).weekday() < 5
