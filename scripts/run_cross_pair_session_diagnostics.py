"""Describe cross-pair session movement relative to frozen research friction.

This is not a strategy, signal generator, backtest, or broker adapter.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_END, DEVELOPMENT_START
from mt5_scalping_agent.research.manifest import write_json_atomic


PAIRS = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCAD": 0.0001}


def main() -> int:
    archive = LocalResearchArchive(Path("data"))
    costs = json.loads(
        Path("reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json")
        .read_text(encoding="utf-8")
    )
    results = {}
    for pair, pip_size in PAIRS.items():
        candles = archive.load_m1(pair, DEVELOPMENT_START, DEVELOPMENT_END)
        base_cost = float(costs["models"][pair]["base"]["round_trip_cost_pips"])
        results[pair] = _diagnostic(candles, pip_size, base_cost)
    report = {
        "purpose": "descriptive session movement versus frozen base friction; not evidence of a trading edge",
        "period": {"start": DEVELOPMENT_START.isoformat(), "end_exclusive": DEVELOPMENT_END.isoformat()},
        "session_clock": "Europe/London and America/New_York civil time with DST",
        "results": results,
    }
    path = Path("reports/cross_pair_feasibility/cross_pair_session_movement_diagnostics.json")
    write_json_atomic(path, report)
    print(f"Report: {path}")
    return 0


def _diagnostic(candles: pd.DataFrame, pip_size: float, base_cost_pips: float) -> dict[str, object]:
    times = candles["time"]
    london_hour = times.dt.tz_convert("Europe/London").dt.hour
    new_york_hour = times.dt.tz_convert("America/New_York").dt.hour
    london = (london_hour >= 8) & (london_hour < 13)
    new_york = (new_york_hour >= 8) & (new_york_hour < 13)
    labels = np.select(
        [london & new_york, london, new_york],
        ["london_new_york_overlap", "london_only", "new_york_only"],
        default="other",
    )
    movement = pd.DataFrame({
        "session": labels,
        "range_pips": (candles["high"] - candles["low"]) / pip_size,
        "body_pips": (candles["close"] - candles["open"]).abs() / pip_size,
    })
    output: dict[str, object] = {"base_round_trip_cost_pips": base_cost_pips, "sessions": {}}
    for session, group in movement.groupby("session", sort=True):
        range_pips = group["range_pips"]
        body_pips = group["body_pips"]
        range_p95 = float(range_pips.quantile(0.95))
        output["sessions"][str(session)] = {
            "m1_count": int(len(group)),
            "range_pips": {"median": float(range_pips.median()), "p95": range_p95},
            "absolute_body_pips": {"median": float(body_pips.median()), "p95": float(body_pips.quantile(0.95))},
            "p95_range_to_base_cost_ratio": range_p95 / base_cost_pips,
        }
    return output


if __name__ == "__main__":
    raise SystemExit(main())
