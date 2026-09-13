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


def test_fixed_discovery_spread_excludes_zero_without_changing_eligible_population() -> None:
    eligible = pd.DataFrame({"spread_pips": [0.0, 1.0, 3.0], "anchor_utc_ns": [10, 20, 30]})
    before = eligible.copy(deep=True)

    fixed = runner._fixed_discovery_spread_pips(eligible)

    assert fixed == pytest.approx(2.0)
    pd.testing.assert_frame_equal(eligible, before)
    assert len(eligible) == 3  # zero remains eligible for raw-pip estimands


@pytest.mark.parametrize("values", [[], [0.0], [0.0, np.nan], [np.nan, np.inf]])
def test_fixed_discovery_spread_fails_closed_without_positive_finite_population(values: list[float]) -> None:
    with pytest.raises(runner.InvalidResearchRun, match="strictly-positive"):
        runner._fixed_discovery_spread_pips(pd.DataFrame({"spread_pips": values}))
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
    run_id="phase22b_20260912T120000Z"; code="d" * 40
    runtime=root/"runtime"/run_id; private=runtime/"staging"; private.mkdir(parents=True)
    identity={"run_id":run_id,"task_id":"PH22B-RI-002","specification_hash":runner.SPEC_SHA256,"code_commit":code,"authorized_data_windows":[str(year) for year in runner.YEARS],"authorized_symbols":list(runner.PAIRS),"authoritative_binding":{"repository":str(root.resolve())}}
    (runtime/"identity.json").write_text(json.dumps(identity),encoding="utf-8")
    args = argparse.Namespace(repository=root, control_plane_only=False, run_id=run_id, code_version=code, output_root=private)
    result = runner.execute(args, byte_reader=lambda locator: (_ for _ in ()).throw(AssertionError("synthetic E2E must not read market data")))
    assert result["status"] == "DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW"
    artifact = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
    score = artifact["analysis"]["score_diagnostic"]
    assert score["role"].endswith("NON_GATING") and artifact["analysis"]["diagnostic_provenance"]["included_in_advancement_or_fdr"] is False
    assert artifact["provenance"]["implementation_benchmark"]["canonical_sha256"] == runner.BENCHMARK_SHA256
    assert artifact["evidence"]["provenance_hashes"]["implementation_benchmark"] == runner.BENCHMARK_SHA256
    assert (private / "governance/results/PH22B-RI-002.json").is_file()
    assert not (root / "governance/results/PH22B-RI-002.json").exists()
    with pytest.raises(runner.InvalidResearchRun, match="immutable publication"):
        runner.execute(args, byte_reader=lambda locator: b"")


def _private_output_fixture(tmp_path: Path, **identity_updates):
    root = _synthetic_repository(tmp_path)
    run_id = "phase22b_20260913T180000Z"
    code = "e" * 40
    runtime = root / "runtime" / run_id
    private = runtime / "staging"
    private.mkdir(parents=True)
    identity = {
        "run_id": run_id, "task_id": "PH22B-RI-002",
        "specification_hash": runner.SPEC_SHA256, "code_commit": code,
        "authorized_data_windows": ["2019", "2020", "2021"],
        "authorized_symbols": list(runner.PAIRS),
        "authoritative_binding": {"repository": str(root.resolve())},
    }
    identity.update(identity_updates)
    (runtime / "identity.json").write_text(json.dumps(identity), encoding="utf-8")
    return root, run_id, code, argparse.Namespace(output_root=private)


def test_string_year_manifest_round_trip_produces_canonical_integer_domain(tmp_path: Path) -> None:
    serialized = json.loads(json.dumps({"years": ["2019", "2020", "2021"]}))
    assert runner._canonical_authorized_years(serialized["years"], "years") == runner.YEARS


def test_valid_supervisor_identity_matches_runner_without_data_read(tmp_path: Path) -> None:
    root, run_id, code, args = _private_output_fixture(tmp_path)
    assert runner._private_output_root(args, root, run_id, code) == args.output_root.resolve()


@pytest.mark.parametrize("years", [
    ["2022"], ["2023"], ["2024"], ["2019", "2020", "2021", "2022"],
    ["2019.0", "2020", "2021"], ["02019", "2020", "2021"],
    [2019, 2020, 2021], [2019.5, "2020", "2021"], [True, "2020", "2021"],
    [None, "2020", "2021"], [], ["2019", "2019", "2021"],
])
def test_invalid_or_unauthorized_year_identity_fails_before_data_access(tmp_path: Path, years: object) -> None:
    root, run_id, code, args = _private_output_fixture(tmp_path, authorized_data_windows=years)
    with pytest.raises(runner.InvalidResearchRun):
        runner._private_output_root(args, root, run_id, code)


@pytest.mark.parametrize("update", [
    {"specification_hash": "0" * 64}, {"authorized_symbols": ["EURUSD"]},
    {"task_id": "PH22B-RI-001"}, {"run_id": "phase22b_20260913T180001Z"},
])
def test_non_year_supervisor_identity_mismatch_still_fails(tmp_path: Path, update: dict) -> None:
    root, run_id, code, args = _private_output_fixture(tmp_path, **update)
    with pytest.raises(runner.InvalidResearchRun, match="supervisor identity mismatch"):
        runner._private_output_root(args, root, run_id, code)


def test_failed_predecessor_is_immutable_non_scientific() -> None:
    incident = json.loads((ROOT / "governance/incidents/PH22B-DURABLE-LAUNCH-FAILURE-002.json").read_text(encoding="utf-8"))
    assert incident["run_id"] == "phase22b_20260913T163443Z"
    assert incident["classification"] == "INVALID_FAILED_NON_SCIENTIFIC"
    assert incident["run_id_reusable"] is False
    assert incident["market_data_accessed"] is False