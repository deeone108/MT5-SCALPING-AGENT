from __future__ import annotations

from pathlib import Path

import pandas as pd

import pytest

from mt5_scalping_agent.research.cross_pair import (
    CrossPairCostModel,
    CrossPairDevelopmentSpec,
    CrossPairResearchError,
    evaluate_pair_development,
    load_frozen_cost_model,
)
from mt5_scalping_agent.risk import RiskLimits, SymbolRiskSpec



def _symbol(name: str) -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol=name,
        point=0.001 if name == "USDJPY" else 0.00001,
        tick_size=0.001 if name == "USDJPY" else 0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )


@pytest.mark.parametrize(("name", "pip"), (("EURUSD", 0.0001), ("GBPUSD", 0.0001), ("USDJPY", 0.01), ("USDCAD", 0.0001)))
def test_pair_spec_uses_correct_pip_convention(name: str, pip: float) -> None:
    assert CrossPairDevelopmentSpec(name, _symbol(name)).pip_size == pip


def test_pair_spec_rejects_mismatched_broker_economics() -> None:
    with pytest.raises(CrossPairResearchError, match="does not match"):
        CrossPairDevelopmentSpec("GBPUSD", _symbol("USDCAD"))


def test_pair_spec_requires_every_development_annual_file(tmp_path: Path) -> None:
    spec = CrossPairDevelopmentSpec("USDCAD", _symbol("USDCAD"))
    with pytest.raises(CrossPairResearchError, match="incomplete development archive"):
        spec.load_development_m1(tmp_path)


def test_cost_model_requires_evidence_and_uses_pair_pip_value(tmp_path: Path) -> None:
    report = tmp_path / "spread.json"
    report.write_text("{}", encoding="utf-8")
    spec = CrossPairDevelopmentSpec("USDJPY", _symbol("USDJPY"))
    costs = CrossPairCostModel(3.0, 1.0, 2.0, report, "broker contract page")

    assert costs.round_trip_cost_pips(spec) == pytest.approx(0.8)


def test_cost_model_rejects_missing_calibration_report(tmp_path: Path) -> None:
    with pytest.raises(CrossPairResearchError, match="calibration report"):
        CrossPairCostModel(2.0, 1.0, 2.0, tmp_path / "missing.json", "broker page")

def test_loads_matching_frozen_cost_scenario(tmp_path: Path) -> None:
    report = tmp_path / "spread.json"
    report.write_text("{}", encoding="utf-8")
    document = {
        "schema_version": 1,
        "models": {
            "USDCAD": {
                "pip_size": 0.0001,
                "spread_report": "spread.json",
                "commission_per_lot_per_side_usd": 2.0,
                "commission_basis": "published schedule",
                "base": {"spread_points": 4.0, "slippage_points": 1.0, "round_trip_cost_pips": 0.9},
                "stress": {"spread_points": 5.0, "slippage_points": 2.0, "round_trip_cost_pips": 1.1},
            }
        },
    }
    source = tmp_path / "costs.json"
    source.write_text(__import__("json").dumps(document), encoding="utf-8")

    model = load_frozen_cost_model(
        source,
        CrossPairDevelopmentSpec("USDCAD", _symbol("USDCAD")),
        "base",
        project_root=tmp_path,
    )

    assert model.spread_points == 4.0
    assert model.slippage_points == 1.0

def test_evaluator_rejects_invalid_research_volume_before_archive_access(tmp_path: Path) -> None:
    report = tmp_path / "spread.json"
    report.write_text("{}", encoding="utf-8")
    spec = CrossPairDevelopmentSpec("GBPUSD", _symbol("GBPUSD"))
    costs = CrossPairCostModel(2.0, 1.0, 2.0, report, "broker page")

    with pytest.raises(CrossPairResearchError, match="fixed research volume"):
        evaluate_pair_development(
            spec,
            costs,
            lambda _: None,
            archive_root=tmp_path,
            risk_limits=RiskLimits(),
            fixed_volume_lots=0.0,
        )

def test_evaluator_delegates_to_backtester_on_development_candles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "spread.json"
    report.write_text("{}", encoding="utf-8")
    candles = pd.DataFrame({
        "time": pd.date_range("2020-01-01", periods=3, freq="min", tz="UTC"),
        "open": [1.2, 1.2, 1.2],
        "high": [1.21, 1.21, 1.21],
        "low": [1.19, 1.19, 1.19],
        "close": [1.2, 1.2, 1.2],
        "tick_volume": [1.0, 1.0, 1.0],
    })
    monkeypatch.setattr(
        CrossPairDevelopmentSpec,
        "load_development_m1",
        lambda self, root: candles,
    )
    result = evaluate_pair_development(
        CrossPairDevelopmentSpec("GBPUSD", _symbol("GBPUSD")),
        CrossPairCostModel(2.0, 1.0, 2.0, report, "broker page"),
        lambda _: None,
        archive_root=tmp_path,
        risk_limits=RiskLimits(),
    )

    assert result.trade_count == 0
    assert result.emitted_signal_count == 0
