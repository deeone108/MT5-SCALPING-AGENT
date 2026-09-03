"""Summarize recorded read-only MT5 tick/spread data for research calibration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mt5_scalping_agent.data.tick_analysis import TickAnalysisError, analyze_tick_spreads


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze freshness and spread statistics from a tick CSV.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--maximum-tick-age-seconds", type=float, default=5.0)
    parser.add_argument("--broker-time-offset-hours", type=float, default=0.0)
    parser.add_argument("--maximum-clock-skew-seconds", type=float, default=0.0)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    try:
        print(json.dumps(analyze_tick_spreads(
            args.path, args.maximum_tick_age_seconds, args.broker_time_offset_hours,
            args.maximum_clock_skew_seconds
        ), indent=2))
        return 0
    except (TickAnalysisError, ValueError) as error:
        print(f"Tick analysis failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
