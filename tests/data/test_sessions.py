from datetime import UTC, date, datetime

import pytest

from mt5_scalping_agent.data.sessions import (
    MarketSession,
    active_sessions,
    new_york_session_subsection,
    session_bounds_utc,
    session_name,
)


@pytest.mark.parametrize(
    ("session", "local_date", "expected_start", "expected_end"),
    [
        (MarketSession.LONDON, date(2025, 1, 15), datetime(2025, 1, 15, 8, tzinfo=UTC), datetime(2025, 1, 15, 13, tzinfo=UTC)),
        (MarketSession.LONDON, date(2025, 7, 15), datetime(2025, 7, 15, 7, tzinfo=UTC), datetime(2025, 7, 15, 12, tzinfo=UTC)),
        (MarketSession.NEW_YORK, date(2025, 1, 15), datetime(2025, 1, 15, 13, tzinfo=UTC), datetime(2025, 1, 15, 18, tzinfo=UTC)),
        (MarketSession.NEW_YORK, date(2025, 7, 15), datetime(2025, 7, 15, 12, tzinfo=UTC), datetime(2025, 7, 15, 17, tzinfo=UTC)),
    ],
)
def test_session_bounds_follow_local_dst(
    session: MarketSession,
    local_date: date,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    assert session_bounds_utc(session, local_date) == (expected_start, expected_end)


def test_session_membership_uses_half_open_bounds() -> None:
    assert active_sessions(datetime(2025, 1, 15, 8, tzinfo=UTC)) == (MarketSession.LONDON,)
    assert session_name(datetime(2025, 1, 15, 7, 59, tzinfo=UTC)) == "off_session"
    assert session_name(datetime(2025, 7, 15, 12, tzinfo=UTC)) == "new_york"


def test_session_membership_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        active_sessions(datetime(2025, 1, 15, 8))


def test_new_york_subsections_follow_local_clock_across_dst() -> None:
    assert new_york_session_subsection(
        datetime(2025, 1, 15, 13, 30, tzinfo=UTC)
    ) == "08:00-09:00"
    assert new_york_session_subsection(
        datetime(2025, 7, 15, 12, 30, tzinfo=UTC)
    ) == "08:00-09:00"
    assert new_york_session_subsection(
        datetime(2025, 1, 15, 12, 30, tzinfo=UTC)
    ) == "outside_08:00-13:00"


def test_new_york_subsection_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        new_york_session_subsection(datetime(2025, 1, 15, 13, 30))