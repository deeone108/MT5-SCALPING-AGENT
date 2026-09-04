"""Preregistered Phase 21C one-leg evaluator; research only, never execution."""
from __future__ import annotations
from collections.abc import Mapping
from pathlib import Path
import json
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.cross_pair_edge_discovery import USD_SIGN, pip_size
from mt5_scalping_agent.research.relative_value_discovery import dedup
from mt5_scalping_agent.research.time_alignment import validated_time_index

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
HOLDING_MINUTES = 60
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 21_003

def target_reversion_direction(pair: str, residual: float) -> int:
    name = pair.upper()
    if name not in PAIRS:
        raise ValueError(f"unsupported pair: {pair}")
    if not np.isfinite(residual) or residual == 0:
        raise ValueError("residual must be finite and non-zero")
    return int(-np.sign(residual) * USD_SIGN[name])

def load_canonical_costs(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    models = document.get("models", {})
    if document.get("schema_version") != 1 or set(models) != set(PAIRS):
        raise ValueError("invalid canonical cost model")
    return models

def _deduplicate(events: pd.DataFrame) -> pd.DataFrame:
    pieces = [dedup(group.sort_values("event_time"), HOLDING_MINUTES) for _, group in events.groupby("pair", sort=False)]
    return pd.concat(pieces, ignore_index=True) if pieces else events.iloc[:0].copy()
