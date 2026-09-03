"""Quality checks and descriptive statistics for recorded broker tick spreads."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mt5_scalping_agent.data.sessions import session_name


class TickAnalysisError(ValueError):
    """Raised when a tick-spread CSV cannot be used for calibration."""


_REQUIRED_COLUMNS = frozenset({"observed_at", "tick_time", "symbol", "bid", "ask", "spread_points"})
_NORMAL_SESSIONS = ("london", "new_york", "london_new_york")


def analyze_tick_spreads(
    path: Path,
    maximum_tick_age_seconds: float = 5.0,
    broker_time_offset_hours: float = 0.0,
    maximum_clock_skew_seconds: float = 0.0,
) -> dict[str, object]:
    """Return freshness-aware, session-specific broker spread statistics."""
    if maximum_tick_age_seconds < 0:
        raise ValueError("maximum_tick_age_seconds cannot be negative")
    if not -14 <= broker_time_offset_hours <= 14:
        raise ValueError("broker_time_offset_hours must be between -14 and 14")
    if maximum_clock_skew_seconds < 0:
        raise ValueError("maximum_clock_skew_seconds cannot be negative")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as error:
        raise TickAnalysisError(f"could not read tick CSV: {path}") from error
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing or frame.empty:
        raise TickAnalysisError("tick CSV is empty or missing required columns")
    try:
        frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="raise", format="mixed")
        frame["tick_time"] = pd.to_datetime(frame["tick_time"], utc=True, errors="raise", format="mixed")
        frame["spread_points"] = pd.to_numeric(frame["spread_points"], errors="raise")
    except (TypeError, ValueError) as error:
        raise TickAnalysisError("tick CSV contains invalid timestamps or spread values") from error
    normalized_tick_time = frame["tick_time"] - pd.to_timedelta(broker_time_offset_hours, unit="h")
    ages = (frame["observed_at"] - normalized_tick_time).dt.total_seconds()
    if (ages < -maximum_clock_skew_seconds).any() or (frame["spread_points"] < 0).any():
        raise TickAnalysisError("tick CSV contains invalid negative ages or spreads")
    fresh_frame = frame.loc[ages <= maximum_tick_age_seconds, ["observed_at", "spread_points"]].copy()
    fresh_frame["session"] = fresh_frame["observed_at"].map(
        lambda value: session_name(value.to_pydatetime())
    )
    sessions = _session_summaries(fresh_frame)
    normal_p95 = [item["spread_points"]["p95"] for item in sessions if item["session"] in _NORMAL_SESSIONS]
    return {
        "symbol": str(frame["symbol"].iloc[0]),
        "record_count": len(frame),
        "fresh_record_count": len(fresh_frame),
        "stale_record_count": int((ages > maximum_tick_age_seconds).sum()),
        "maximum_tick_age_seconds": maximum_tick_age_seconds,
        "broker_time_offset_hours": broker_time_offset_hours,
        "maximum_clock_skew_seconds": maximum_clock_skew_seconds,
        "median_tick_age_seconds": float(ages.median()),
        "maximum_tick_age_observed_seconds": float(ages.max()),
        "spread_points_all": _spread_summary(frame["spread_points"]),
        "spread_points_fresh": _spread_summary(fresh_frame["spread_points"]),
        "fresh_session_spreads": sessions,
        "recommended_conservative_spread_points": max(normal_p95) if normal_p95 else None,
    }



def _session_summaries(fresh_frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {"session": session, "record_count": len(group), "spread_points": _spread_summary(group["spread_points"])}
        for session, group in fresh_frame.groupby("session", sort=True)
    ]


def _spread_summary(spreads: pd.Series) -> dict[str, float | None]:
    if spreads.empty:
        return {"minimum": None, "median": None, "p95": None, "maximum": None}
    return {
        "minimum": round(float(spreads.min()), 10),
        "median": round(float(spreads.median()), 10),
        "p95": round(float(spreads.quantile(0.95)), 10),
        "maximum": round(float(spreads.max()), 10),
    }
