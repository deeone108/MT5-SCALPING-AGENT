from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_SPEC = importlib.util.spec_from_file_location("phase22b_development_runner", ROOT / "scripts" / "run_phase22b_development.py")
assert MODULE_SPEC and MODULE_SPEC.loader
runner = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(runner)


def _synthetic_repository(tmp_path: Path) -> Path:
    for relative in (
        runner.SPEC,
        runner.TASK,
        runner.BENCHMARK,
        "governance/PHASE22B_EVIDENCE.schema.json",
        "governance/RESULT_MANIFEST.schema.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    task = json.loads((tmp_path / runner.TASK).read_text(encoding="utf-8"))
    state = {
        "research_spec_hash": runner.SPEC_SHA256,
        "allowed_data_windows": ["2019", "2020", "2021"],
        "locked_data_windows": ["2022", "2023"],
        "forbidden_data_windows": ["2024+"],
    }
    state_path = tmp_path / runner.STATE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return tmp_path


def test_benchmark_evidence_absent_or_mismatched_fails_closed(tmp_path: Path) -> None:
    root = _synthetic_repository(tmp_path)
    (root / runner.BENCHMARK).unlink()
    with pytest.raises(runner.InvalidResearchRun, match="benchmark evidence absent"):
        runner._verified_benchmark(root)
    shutil.copy2(ROOT / runner.BENCHMARK, root / runner.BENCHMARK)
    value = json.loads((root / runner.BENCHMARK).read_text(encoding="utf-8"))
    value["measurements"]["wall_seconds"] += 1
    (root / runner.BENCHMARK).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(runner.InvalidResearchRun, match="benchmark evidence hash mismatch"):
        runner._verified_benchmark(root)


def test_checked_in_state_control_plane_binds_v12_without_loading_data(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_data_load(*args, **kwargs):
        raise AssertionError("control-plane validation must not invoke data loading")

    monkeypatch.setattr(runner, "_build_rows", forbidden_data_load)
    args = argparse.Namespace(repository=ROOT, control_plane_only=True, run_id="", code_version="")
    result = runner.execute(args, byte_reader=forbidden_data_load)
    assert result["status"] == "CONTROL_PLANE_VALIDATED_NO_DATA_READ"
    assert result["specification_hash"] == runner.SPEC_SHA256 == "12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
    assert result["years"] == [2019, 2020, 2021]

def test_synthetic_runner_e2e_binds_authority_scores_validates_and_publishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _synthetic_repository(tmp_path)
    rows = pd.DataFrame({
        "pair": ["EURUSD"] * 8,
        "utc_day": ["2019-01-01"] * 2 + ["2019-01-02"] * 2 + ["2019-01-03"] * 2 + ["2019-01-04"] * 2,
        "anchor_utc_ns": np.arange(8, dtype=np.int64),
        "source_row_ordinal": np.arange(8, dtype=np.int64),
        "exposure": ["TIGHT", "WIDE"] * 4,
        "Y_RAW_ABS_60S_PIPS": [1.0, 2.0, 1.5, 2.8, 1.2, 2.1, 1.9, 3.2],
    })
    stage = {"models": {"M4": {"exposure__WIDE": -0.1}}, "outcomes": {}, "amplification_ratio": 1.0,
             "primary_bootstrap": {"ci_low": -0.2, "ci_high": -0.01}, "raw_p_values": {}, "fdr": {},
             "interactions": {}, "attenuation": {}}
    diagnostics = {"pair": {"EURUSD": -0.1}, "session": {"LONDON": -0.1}, "year": {"2019": -0.1, "2020": -0.1, "2021": -0.1},
                   "negative_pair_count": 1, "negative_core_session_count": 1, "largest_pair_fraction": 1.0,
                   "top_five_day_fraction": 0.2, "largest_month_fraction": 0.2}
    monkeypatch.setattr(runner, "_build_rows", lambda *args, **kwargs: (rows, {"catalogs": {}, "monthly_units": [], "frozen_development": {}}))
    monkeypatch.setattr(runner, "analyse_stage", lambda *args, **kwargs: stage)
    monkeypatch.setattr(runner, "stability_diagnostics", lambda *args, **kwargs: diagnostics)
    monkeypatch.setattr(runner, "development_gate_truths", lambda *args, **kwargs: {"synthetic": True})
    monkeypatch.setattr(runner, "model_contract", lambda *args, **kwargs: {"response": "Y_RAW_ABS_60S_PIPS", "predictors": ["intercept", "exposure__WIDE"], "coefficient_names": ["intercept", "exposure__WIDE"]})
    args = argparse.Namespace(repository=root, control_plane_only=False, run_id="phase22b_20260912T120000Z", code_version="d" * 40)
    result = runner.execute(args, byte_reader=lambda locator: (_ for _ in ()).throw(AssertionError("synthetic E2E must not read market data")))
    assert result["status"] == "DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW"
    artifact = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
    score = artifact["analysis"]["score_diagnostic"]
    assert score["role"].endswith("NON_GATING") and artifact["analysis"]["diagnostic_provenance"]["included_in_advancement_or_fdr"] is False
    assert artifact["provenance"]["implementation_benchmark"]["canonical_sha256"] == runner.BENCHMARK_SHA256
    assert artifact["evidence"]["provenance_hashes"]["implementation_benchmark"] == runner.BENCHMARK_SHA256
    assert (root / "governance/results/PH22B-RI-002.json").is_file()
    with pytest.raises(runner.InvalidResearchRun, match="immutable publication"):
        runner.execute(args, byte_reader=lambda locator: b"")
