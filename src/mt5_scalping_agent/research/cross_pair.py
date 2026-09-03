"""Strict development-data contracts for cross-pair research.

This module deliberately contains no strategy, execution, or cost assumptions.
It makes any later comparison declare pair-specific broker economics explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path

import pandas as pd

from mt5_scalping_agent.backtesting import BacktestConfig, BacktestResult, CandleBacktester, PositionSizingMode
from mt5_scalping_agent.backtesting.engine import Strategy

from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


DEVELOPMENT_START = datetime(2019, 1, 1, tzinfo=UTC)
DEVELOPMENT_END = datetime(2024, 1, 1, tzinfo=UTC)
_PIP_SIZES = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCAD": 0.0001}


class CrossPairResearchError(ValueError):
    """Raised when a cross-pair development request is incomplete or unsafe."""


@dataclass(frozen=True)
class CrossPairCostModel:
    """Explicit per-trade friction inputs for a single broker/pair contract."""

    spread_points: float
    slippage_points: float
    commission_per_lot_per_side_usd: float
    calibration_report: Path
    commission_evidence: str

    def __post_init__(self) -> None:
        values = (
            self.spread_points,
            self.slippage_points,
            self.commission_per_lot_per_side_usd,
        )
        if any(not isfinite(value) or value < 0 for value in values):
            raise CrossPairResearchError("pair cost inputs must be finite and nonnegative")
        if not self.calibration_report.is_file():
            raise CrossPairResearchError("pair cost model requires a calibration report")
        if not self.commission_evidence.strip():
            raise CrossPairResearchError("pair cost model requires commission evidence")

    def round_trip_cost_pips(self, spec: "CrossPairDevelopmentSpec") -> float:
        pip_value = spec.pip_size / spec.broker_symbol.tick_size * spec.broker_symbol.tick_value
        if pip_value <= 0:
            raise CrossPairResearchError("pair pip value must be positive")
        price_cost = (self.spread_points + self.slippage_points) * spec.broker_symbol.point
        commission_cost = 2 * self.commission_per_lot_per_side_usd / pip_value
        return price_cost / spec.pip_size + commission_cost

@dataclass(frozen=True)
class CrossPairDevelopmentSpec:
    """Pair identity and broker economics required for a fair development run."""

    symbol: str
    broker_symbol: SymbolRiskSpec

    def __post_init__(self) -> None:
        normalized = self.symbol.upper()
        if normalized not in _PIP_SIZES:
            raise CrossPairResearchError(f"unsupported cross-pair symbol: {self.symbol}")
        if self.broker_symbol.symbol.upper() != normalized:
            raise CrossPairResearchError("broker symbol specification does not match pair")

    @property
    def normalized_symbol(self) -> str:
        return self.symbol.upper()

    @property
    def pip_size(self) -> float:
        return _PIP_SIZES[self.normalized_symbol]

    def annual_paths(self, archive_root: Path) -> tuple[Path, ...]:
        return tuple(
            archive_root / "dukascopy_annual" / f"{self.normalized_symbol}_m1_{year}.csv.gz"
            for year in range(DEVELOPMENT_START.year, DEVELOPMENT_END.year)
        )

    def load_development_m1(self, archive_root: Path) -> pd.DataFrame:
        missing = [path for path in self.annual_paths(archive_root) if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise CrossPairResearchError(f"incomplete development archive: {joined}")
        return LocalResearchArchive(archive_root).load_m1(
            self.normalized_symbol, DEVELOPMENT_START, DEVELOPMENT_END
        )


def load_frozen_cost_model(
    path: Path,
    spec: CrossPairDevelopmentSpec,
    scenario: str,
    *,
    project_root: Path = Path.cwd(),
) -> CrossPairCostModel:
    """Load one predeclared pair/scenario model and reject drift or omissions."""
    if scenario not in {"base", "stress"}:
        raise CrossPairResearchError("cost scenario must be base or stress")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        entry = document["models"][spec.normalized_symbol]
        selected = entry[scenario]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise CrossPairResearchError("could not load frozen pair cost model") from error
    if document.get("schema_version") != 1 or entry.get("pip_size") != spec.pip_size:
        raise CrossPairResearchError("frozen pair cost model does not match pair pip convention")
    report = project_root / str(entry.get("spread_report", ""))
    model=CrossPairCostModel(
        spread_points=float(selected["spread_points"]),
        slippage_points=float(selected["slippage_points"]),
        commission_per_lot_per_side_usd=float(entry["commission_per_lot_per_side_usd"]),
        calibration_report=report,
        commission_evidence=str(entry["commission_basis"]),
    )
    declared=float(selected["round_trip_cost_pips"])
    if abs(model.round_trip_cost_pips(spec)-declared)>1e-6:
        raise CrossPairResearchError("declared round-trip cost does not match canonical components")
    return model

def evaluate_pair_development(
    spec: CrossPairDevelopmentSpec,
    cost_model: CrossPairCostModel,
    strategy: Strategy,
    *,
    archive_root: Path,
    risk_limits: RiskLimits,
    initial_balance: float = 10_000.0,
    fixed_volume_lots: float = 1.0,
) -> BacktestResult:
    """Run a supplied frozen strategy on exactly one pair's isolated development data.

    The caller must provide a pre-registered strategy. This adapter neither selects
    parameters nor accesses post-selection data, broker orders, or live prices.
    """
    if initial_balance <= 0 or fixed_volume_lots <= 0:
        raise CrossPairResearchError("initial balance and fixed research volume must be positive")
    candles = spec.load_development_m1(archive_root)
    config = BacktestConfig(
        initial_balance=initial_balance,
        spread_points=cost_model.spread_points,
        slippage_points=cost_model.slippage_points,
        commission_per_lot_per_side=cost_model.commission_per_lot_per_side_usd,
        position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
        fixed_volume_lots=fixed_volume_lots,
    )
    return CandleBacktester(config, RiskEngine(risk_limits), spec.broker_symbol).run(
        candles, strategy
    )
