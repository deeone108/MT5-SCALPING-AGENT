import copy
import hashlib
import json

import pytest

from mt5_scalping_agent.orchestration.errors import OrchestrationError
from mt5_scalping_agent.orchestration.remediation import (
    AGENT_RESOLVABLE, HUMAN_REQUIRED, classify_findings, detect_deadlock,
    finding_fingerprint, make_remediation_descriptor, record_attempt, validate_loop,
)

H = "a" * 64
R = "b" * 64

def loop():
    return {"schema_version": 1, "loop_id": "PH22B-LOOP-001", "phase": "PHASE_22B_PENDING_DESIGN", "candidate_id": "P22A_SPR_ABS_15s_60s", "state": "REVIEW_REJECTED", "lineage": [], "attempts": [], "current_spec_hash": H, "review_artifacts": [{"path": "review.json", "sha256": R, "decision": "REJECTED"}], "finding_fingerprints": [], "next_transition": "CLASSIFY_FINDINGS", "safety": {"allowed_data_window": [], "live_execution_authorized": False, "review_bypass_authorized": False, "scope_change_authorized": False}}

def finding(code="MODEL_AMBIGUITY"):
    return {"code": code, "severity": "HIGH", "affected_contract": "M1", "required_correction": "freeze matrix", "agent_resolvable": True, "requires_human_authority": False}

def test_agent_resolvable_descriptor_is_no_data_and_preserves_review():
    state = loop(); item = finding()
    descriptor = make_remediation_descriptor(state, [item], task_id="PH22B-REM-004", assigned_role="research_lead")
    assert descriptor["classification"] == AGENT_RESOLVABLE
    assert descriptor["allowed_data_window"] == []
    assert descriptor["source_reviews"] == state["review_artifacts"]
    assert descriptor["finding_fingerprints"] == [finding_fingerprint(item)]

@pytest.mark.parametrize("code", ["DATA_2024_PLUS", "LIVE_ACTIVATION", "SCOPE_CHANGE", "REVIEW_BYPASS", "FROZEN_ARTIFACT_MUTATION"])
def test_hard_boundaries_require_human(code):
    assert classify_findings([finding(code)]) == HUMAN_REQUIRED

def test_unclassified_finding_fails_to_human():
    item = finding(); item.pop("agent_resolvable")
    assert classify_findings([item]) == HUMAN_REQUIRED

def test_safety_state_cannot_authorize_data_live_scope_or_bypass():
    for key, value in [("allowed_data_window", ["2024"]), ("live_execution_authorized", True), ("review_bypass_authorized", True), ("scope_change_authorized", True)]:
        state = loop(); state["safety"][key] = value
        with pytest.raises(OrchestrationError): validate_loop(state)

def test_material_attempt_persists_lineage_and_independent_review_transition():
    state = loop(); d = make_remediation_descriptor(state, [finding()], task_id="REM-1", assigned_role="research_lead")
    out = record_attempt(state, descriptor=d, output_spec_hash="c" * 64, material_change=True)
    assert out["state"] == "PENDING_INDEPENDENT_REVIEW"
    assert out["next_transition"] == "INDEPENDENT_STATISTICAL_AND_QA_REVIEW"
    assert out["lineage"][-1]["from_spec_hash"] == H
    assert out["review_artifacts"] == state["review_artifacts"]

def test_deadlock_uses_evidence_not_retry_count():
    state = loop(); f = finding_fingerprint(finding())
    state["attempts"] = [{"task_id": "old", "input_spec_hash": "d"*64, "output_spec_hash": "c"*64, "finding_fingerprints": [f], "material_change": True}]
    assert detect_deadlock(state, proposed_spec_hash="c"*64, finding_fingerprints=[f], material_change=True)
    assert not detect_deadlock(state, proposed_spec_hash="e"*64, finding_fingerprints=[f], material_change=True)

def test_deadlock_escalates_and_does_not_bypass_review():
    state = loop(); item = finding(); d = make_remediation_descriptor(state, [item], task_id="REM-2", assigned_role="research_lead")
    state["attempts"] = [{"task_id": "old", "input_spec_hash": "d"*64, "output_spec_hash": "c"*64, "finding_fingerprints": d["finding_fingerprints"], "material_change": True}]
    out = record_attempt(state, descriptor=d, output_spec_hash="c"*64, material_change=True)
    assert out["state"] == "HUMAN_GATE_REQUIRED"
    assert out["next_transition"] == "HUMAN_OWNER_DEADLOCK_RESOLUTION"

def test_fingerprint_is_deterministic_and_ignores_nonmaterial_text():
    a = finding(); b = copy.deepcopy(a); b["comment"] = "different prose"
    assert finding_fingerprint(a) == finding_fingerprint(b)

def test_schema_is_valid_json():
    with open("governance/REMEDIATION_LOOP.schema.json", encoding="utf-8") as fh:
        schema = json.load(fh)
    assert schema["properties"]["safety"]["properties"]["allowed_data_window"]["const"] == []
