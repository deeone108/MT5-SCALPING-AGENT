import hashlib
import json
from pathlib import Path

import pytest

from mt5_scalping_agent.orchestration.hashing import canonical_json_bytes
from mt5_scalping_agent.orchestration.task import transition, validate_task
from mt5_scalping_agent.orchestration.result import validate_phase22b_evidence, verify_artifact_hashes
from mt5_scalping_agent.orchestration.errors import OrchestrationError

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "research/phase22b_spec_v3.json"
SPEC_HASH = "6dca34026989fc26bf2e282c48e6a058074bc60ad5df2d476824d5ff16e6a28a"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase22b_remediation_no_data_spec_hash_and_binding():
    spec = load(SPEC_PATH)
    assert hashlib.sha256(canonical_json_bytes(spec)).hexdigest() == SPEC_HASH
    assert (ROOT / "research/phase22b_spec_v3.sha256").read_text().split()[0] == SPEC_HASH
    review_task = load(ROOT / "governance/tasks/PH22B-REVIEW-003.json")
    assert review_task["required_spec_hash"] == SPEC_HASH
    assert review_task["allowed_data"] == review_task["allowed_data_window"] == []
    validate_task(review_task)


def test_model_contract_is_complete_deterministic_and_noncollinear():
    models = load(SPEC_PATH)["models_and_estimands"]["primary_models"]
    required = {"response","predictors","transformations","interactions","categorical_variables","reference_categories","intercept","utc_hour_treatment","session_treatment","pair_treatment","weighting","missing_row_policy","coefficient_names","coefficient_extraction","rank_deficiency","singular_matrix","column_order"}
    for name in ("M0","M1","M2","M3","M4"):
        assert required <= models[name].keys()
        assert models[name]["predictors"] == models[name]["coefficient_names"]
        assert len(models[name]["predictors"]) == len(set(models[name]["predictors"]))
        assert not any("session__" in x for x in models[name]["predictors"])
        assert models[name]["rank_deficiency"] == "PHASE_22B_INVALID_RESEARCH_RUN"


def test_hypothesis_and_bh_families_are_exhaustive():
    spec = load(SPEC_PATH)
    hypotheses = spec["hypothesis_inventory"]
    ids = [h["id"] for h in hypotheses]
    assert len(ids) == len(set(ids))
    assert all({"id","null","alternative","model","statistic","raw_p_value","tail","family"} <= h.keys() for h in hypotheses)
    families = spec["inference"]["multiple_testing"]["families"]
    members = [x for f in families for x in f["members"]]
    assert sorted(members) == sorted(h["id"] for h in hypotheses if h["family"] is not None)
    assert all(f["count"] == len(f["members"]) for f in families)
    assert "H_MIXED" not in ids + members


def test_invalid_run_precedes_scientific_classification():
    spec = load(SPEC_PATH)
    states = spec["terminal_classification_algorithm"]
    assert states[0]["state"] == "PHASE_22B_INVALID_RESEARCH_RUN"
    assert states[0]["kind"] == "operational"
    assert spec["operational_validation"]["precedence"] == "Evaluate before scientific classification."


def test_ai_evidence_schema_is_non_actionable():
    schema = load(ROOT / "governance/PHASE22B_EVIDENCE.schema.json")
    evidence = load(ROOT / "governance/examples/phase22b_evidence.example.json")
    assert schema["properties"]["actionable"]["const"] is False
    assert schema["properties"]["strategy_eligible"]["const"] is False
    assert schema["properties"]["trade_direction"]["type"] == "null"
    validate_phase22b_evidence(evidence)
    for key, value in (("actionable", True), ("strategy_eligible", True), ("trade_direction", "BUY")):
        bad = dict(evidence); bad[key] = value
        with pytest.raises(OrchestrationError):
            validate_phase22b_evidence(bad)


def test_lifecycle_requires_independent_review():
    task = load(ROOT / "governance/tasks/PH22B-REMEDIATION-002.json")
    validate_task(task)
    assert task["status"] == "FROZEN_PENDING_REVIEW"
    assert transition(task, "VALIDATING")["status"] == "VALIDATING"
    assert set(task["required_reviewers"]) == {"statistical_validator", "qa_reviewer"}
    review = load(ROOT / "governance/tasks/PH22B-REVIEW-003.json")
    assert review["status"] == "READY"
    reviews = list((ROOT / "governance/reviews").glob("PH22B-REVIEW-003-*.json"))
    assert len(reviews) == 2
    assert {load(path)["verdict"] for path in reviews} == {"STATISTICAL_VALIDATOR_REJECTED", "QA_REJECTED"}


def test_access_contract_denies_before_reader_and_keeps_candidate_frozen():
    spec = load(SPEC_PATH)
    assert spec["scope"]["primary_candidate_only"] == "P22A_SPR_ABS_15s_60s"
    assert spec["access_contract"]["sequence"][-1] == "file_open"
    assert spec["access_contract"]["deny_before_read"] is True
    assert "2024-01-01" in spec["temporal_partitions"]["forbidden"]

def test_artifact_hashes_are_reproduced_from_contents(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {"artifacts":[{"path":"artifact.json","sha256":digest}],"artifact_hashes":{"artifact.json":digest}}
    verify_artifact_hashes(manifest, tmp_path)
    artifact.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(OrchestrationError):
        verify_artifact_hashes(manifest, tmp_path)