"""DST-aware definitions for the project's London and New York research sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo


class MarketSession(str, Enum):
    """Named market sessions used by research data diagnostics."""

    LONDON = "london"
    NEW_YORK = "new_york"


@dataclass(frozen=True)
class SessionDefinition:
    """A session expressed in its local civil time."""

    name: MarketSession
    timezone: ZoneInfo
    start_local: time
    end_local: time


NEW_YORK_SESSION_SUBSECTIONS = (
    "outside_08:00-13:00",
    "08:00-09:00",
    "09:00-10:00",
    "10:00-11:00",
    "11:00-12:00",
    "12:00-13:00",
)


SESSION_DEFINITIONS = {
    MarketSession.LONDON: SessionDefinition(
        name=MarketSession.LONDON,
        timezone=ZoneInfo("Europe/London"),
        start_local=time(8),
        end_local=time(13),
    ),
    MarketSession.NEW_YORK: SessionDefinition(
        name=MarketSession.NEW_YORK,
        timezone=ZoneInfo("America/New_York"),
        start_local=time(8),
        end_local=time(13),
    ),
}


def session_bounds_utc(session: MarketSession | str, local_date: date) -> tuple[datetime, datetime]:
    """Return UTC bounds for a session on a date in that session's timezone."""
    definition = SESSION_DEFINITIONS[MarketSession(session)]
    start = datetime.combine(local_date, definition.start_local, tzinfo=definition.timezone)
    end_date = local_date + timedelta(days=1) if definition.end_local <= definition.start_local else local_date
    end = datetime.combine(end_date, definition.end_local, tzinfo=definition.timezone)
    return start.astimezone(UTC), end.astimezone(UTC)


def active_sessions(timestamp: datetime) -> tuple[MarketSession, ...]:
    """Return every locally defined session active at a timezone-aware instant."""
    if timestamp.tzinfo is None:
        raise ValueError("session timestamps must be timezone-aware")
    active: list[MarketSession] = []
    for session, definition in SESSION_DEFINITIONS.items():
        local = timestamp.astimezone(definition.timezone)
        start, end = session_bounds_utc(session, local.date())
        normalized = timestamp.astimezone(UTC)
        if start <= normalized < end:
            active.append(session)
    return tuple(active)


def session_name(timestamp: datetime) -> str:
    """Return a stable label, preserving any real London/New York overlap."""
    sessions = active_sessions(timestamp)
    if not sessions:
        return "off_session"
    return "_".join(session.value for session in sessions)


def new_york_session_subsection(timestamp: datetime) -> str:
    """Return a stable one-hour bucket using the New York local civil clock."""
    if timestamp.tzinfo is None:
        raise ValueError("session timestamps must be timezone-aware")
    local = timestamp.astimezone(SESSION_DEFINITIONS[MarketSession.NEW_YORK].timezone)
    if 8 <= local.hour < 13:
        return f"{local.hour:02d}:00-{local.hour + 1:02d}:00"
    return NEW_YORK_SESSION_SUBSECTIONS[0]