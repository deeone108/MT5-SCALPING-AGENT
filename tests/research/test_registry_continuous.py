from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mt5_scalping_agent.research.registry import (
    DEFAULT_REGISTRY_PATH,
    RegistryError,
    ResearchStatus,
    load_research_registry,
    record_completed_continuous_experiment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REGISTRY = PROJECT_ROOT / DEFAULT_REGISTRY_PATH
STRATEGIES = ("new_york_reversal", "new_york_bollinger_rsi_reversal")
TEST_EXPERIMENT_ID = "continuous_development_2019_2023_fixture_v1"


def _continuous_result(strategy: str, net_profit: float) -> dict[str, object]:
    return {
        "strategy": strategy,
        "period": {
            "name": "development",
            "start": "2019-01-01T00:00:00+00:00",
            "end": "2024-01-01T00:00:00+00:00",
            "end_exclusive": True,
            "post_selection_data_used": False,
        },
        "summaries": {
            "complete": {
                "trade_count": 20,
                "total_lots": 2.5,
                "gross_pnl": net_profit + 10.0,
                "total_transaction_cost": 10.0,
                "net_profit": net_profit,
                "gross_expectancy_per_trade": (net_profit + 10.0) / 20,
                "net_expectancy_per_trade": net_profit / 20,
                "profit_factor": 1.25,
                "max_drawdown": 125.0,
            },
            "by_year": [
                {"group": "2019", "net_profit": 10.0},
                {"group": "2020", "net_profit": -5.0},
                {"group": "2021", "net_profit": 8.0},
                {"group": "2022", "net_profit": -3.0},
                {"group": "2023", "net_profit": 4.0},
            ],
            "by_month": [
                {"group": "2019-01", "net_profit": 3.0},
                {"group": "2019-02", "net_profit": -2.0},
                {"group": "2019-03", "net_profit": 1.0},
            ],
        },
    }


def _continuous_report() -> dict[str, object]:
    return {
        "purpose": "continuous 2019-2023 development diagnostics",
        "backtest_assumptions": {
            "spread_points": 2.0,
            "slippage_points": 1.0,
            "commission_per_lot_per_side": 2.0,
        },
        "run_manifest": {"run_id": "continuous_development_evaluation:test"},
        "results": [
            _continuous_result("new_york_reversal", -100.0),
            _continuous_result("new_york_bollinger_rsi_reversal", -50.0),
        ],
    }


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    payload = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8"))
    registry_path = tmp_path / DEFAULT_REGISTRY_PATH
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    evidence_paths = {
        item["report_path"]
        for strategy in payload["strategies"]
        for item in strategy["experiments_performed"]
    }
    for relative in evidence_paths:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, destination)
    report_path = tmp_path / "reports/continuous_evaluation/completed.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_continuous_report(), indent=2), encoding="utf-8")
    return registry_path, report_path


def _record(registry_path: Path, report_path: Path, root: Path):  # type: ignore[no-untyped-def]
    return record_completed_continuous_experiment(
        registry_path=registry_path,
        report_path=report_path,
        experiment_id=TEST_EXPERIMENT_ID,
        cost_model_id="roboforex_ecn_eurusd_v1",
        role="One continuous development run without calendar balance resets.",
        findings={
            "new_york_reversal": "Continuous after-cost development result recorded without changing rejection.",
            "new_york_bollinger_rsi_reversal": "Continuous after-cost development result recorded without changing rejection.",
        },
        project_root=root,
    )


def test_records_completed_continuous_results_atomically_and_idempotently(tmp_path: Path) -> None:
    registry_path, report_path = _workspace(tmp_path)
    original_report = report_path.read_bytes()

    updated = _record(registry_path, report_path, tmp_path)

    for strategy in STRATEGIES:
        record = updated.by_strategy_name()[strategy]
        evidence = record.experiments_performed[-1]
        assert record.status is ResearchStatus.REJECTED
        assert evidence.report_run_id == "continuous_development_evaluation:test"
        assert evidence.continuous_summary is not None
        assert evidence.continuous_summary.positive_years == 3
        assert evidence.continuous_summary.year_count == 5
        assert evidence.continuous_summary.positive_months == 2
        assert evidence.continuous_summary.month_count == 3
    assert report_path.read_bytes() == original_report
    load_research_registry(registry_path, project_root=tmp_path, validate_evidence=True)

    first_updated_at = updated.updated_at
    repeated = _record(registry_path, report_path, tmp_path)
    assert repeated.updated_at == first_updated_at
    for strategy in STRATEGIES:
        ids = [item.experiment_id for item in repeated.by_strategy_name()[strategy].experiments_performed]
        assert ids.count(TEST_EXPERIMENT_ID) == 1


def test_continuous_evidence_detects_report_drift(tmp_path: Path) -> None:
    registry_path, report_path = _workspace(tmp_path)
    _record(registry_path, report_path, tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["results"][0]["summaries"]["complete"]["net_profit"] = 999.0
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RegistryError, match="continuous evidence summary mismatch"):
        load_research_registry(registry_path, project_root=tmp_path, validate_evidence=True)


def test_continuous_registration_rejects_non_development_period(tmp_path: Path) -> None:
    registry_path, report_path = _workspace(tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["results"][0]["period"]["end"] = "2025-01-01T00:00:00+00:00"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RegistryError, match="does not match permitted development dataset"):
        _record(registry_path, report_path, tmp_path)


def test_continuous_registration_rejects_checkpoint_file(tmp_path: Path) -> None:
    registry_path, _ = _workspace(tmp_path)
    checkpoint = tmp_path / "reports/run.checkpoint.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(RegistryError, match="checkpoint cannot be registered"):
        _record(registry_path, checkpoint, tmp_path)
