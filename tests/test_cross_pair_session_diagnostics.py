from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


MODULE_PATH = Path("scripts/run_cross_pair_session_diagnostics.py")
SPEC = importlib.util.spec_from_file_location("cross_pair_sessions", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_session_diagnostic_uses_dst_aware_london_new_york_labels() -> None:
    candles = pd.DataFrame({
        "time": pd.to_datetime([
            "2020-03-23T12:00:00Z",  # London 12:00 and New York 08:00
            "2020-01-15T09:00:00Z",  # London only
            "2020-01-15T15:00:00Z",  # New York only
            "2020-01-15T03:00:00Z",  # neither
        ], utc=True),
        "open": [1.0] * 4,
        "high": [1.0002] * 4,
        "low": [1.0] * 4,
        "close": [1.0001] * 4,
        "tick_volume": [1.0] * 4,
    })

    report = MODULE._diagnostic(candles, 0.0001, 1.0)

    assert set(report["sessions"]) == {
        "london_new_york_overlap", "london_only", "new_york_only", "other"
    }
    assert report["sessions"]["london_new_york_overlap"]["range_pips"]["p95"] == pytest.approx(2.0)
