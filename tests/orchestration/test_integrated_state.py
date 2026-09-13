from pathlib import Path
from mt5_scalping_agent.orchestration.state import StateStore
from mt5_scalping_agent.orchestration.validator import load_json, validate_ledger
ROOT = Path(__file__).resolve().parents[2]
V12_SHA256 = "12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
def test_integrated_project_state_is_valid_and_fail_closed():
    state = StateStore(ROOT / "governance/state/project_state.json").read()
    assert state["current_phase"] == "PHASE_22B_RETROSPECTIVE_DEVELOPMENT"
    assert state["live_execution_authorized"] is False
    assert state["allowed_data_windows"] == ["2019", "2020", "2021"]
    assert state["locked_data_windows"] == ["2022", "2023"]
    assert state["forbidden_data_windows"] == ["2024+"]
    assert state["active_tasks"] == ["PH22B-RI-002", "PH22B-RUNTIME-004"]
    assert state["status"] == "BLOCKED"
    assert state["phase_status"] == "BLOCKED"
    assert state["gates"]["implementation"]["status"] == "PASSED"
    assert state["gates"]["implementation"]["evidence_sha256"] == "79ba4c3fc004b317c799f5d4ff1edae13dad5828d32c9e0343ce3400dd03a262"
    assert state["gates"]["runtime_identity"]["status"] == "PASSED"
    assert state["gates"]["runtime_identity"]["evidence_sha256"] == "8693daa1b91898cf2b42aa218d52137cbcf7caee40bafa6f09dca07c633c1bb3"
    assert state["last_validated_commit"] == "2171ac2c6d5b7e8f8824faf7d64562164164bf60"
    assert state["research_spec_hash"] == V12_SHA256
    assert state["spec_sha256"] == V12_SHA256
def test_integrated_ledger_records_accepted_phase22a():
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    completion = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22A_COMPLETION")
    assert completion["final_report_sha256"] == "05910f453b7ccff64748fe90ff35b3195ccb1c5fa5653f21cd954a8a4112ee4a"
    assert completion["concentration_qualified"] == 22
    assert completion["accessed_2024_plus"] is False

def test_phase22b_v12_ledger_binding_preserves_authority():
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    binding = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22B_V12_FREEZE_BINDING")
    assert binding["specification_path"] == "research/phase22b_spec_v12.json"
    assert binding["specification_sha256"] == V12_SHA256
    assert binding["active_task"] == "PH22B-RI-002"
    assert binding["allowed_years"] == [2019, 2020, 2021]
    assert binding["locked_years"] == [2022, 2023]
    assert binding["forbidden"] == "2024+"
    assert binding["phase_advanced"] is False
    assert binding["data_authority_changed"] is False
    assert binding["strategy_authorized"] is False
    assert binding["pnl_authorized"] is False
    assert binding["execution_authorized"] is False
    assert binding["live_authorized"] is False


def test_phase22b_v12_implementation_readiness_does_not_unlock_later_data():
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    readiness = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22B_V12_IMPLEMENTATION_READINESS")
    assert readiness["reviewed_implementation_commit"] == "e548dd244812a689b49666e98e56e2b27facddd7"
    assert readiness["statistical_review_sha256"] == "014098ccd3b158e6e3047914c8e8828cfba9eaafaaba380792e088d4ae37004b"
    assert readiness["qa_result_sha256"] == "01d79f0dd43b8461ae04243d34c4112e2305dd9d2889b0c616324989c0a8822a"
    assert readiness["allowed_years"] == [2019, 2020, 2021]
    assert readiness["locked_years"] == [2022, 2023]
    assert readiness["confirmation_unlocked"] is False
    assert readiness["phase_advanced"] is False
    assert readiness["strategy_authorized"] is False
    assert readiness["pnl_authorized"] is False
    assert readiness["execution_authorized"] is False
    assert readiness["live_authorized"] is False
    assert not (ROOT / "governance/results/PH22B-RI-002.json").exists()


def test_phase22b_corrected_implementation_readiness_and_failed_run_provenance():
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    failed = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22B_FAILED_RUN_20260912T124222Z")
    assert failed["status"] == "FAIL_CLOSED_NO_ARTIFACTS"
    assert failed["research_evidence_accepted"] is False
    assert failed["development_artifact_published"] is False
    assert failed["result_manifest_published"] is False
    current = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22B_V12_IMPLEMENTATION_READINESS_613AED3")
    assert current["reviewed_implementation_commit"] == "613aed3fd69594e062c4ecfee7e52826d6f3a0a4"
    assert current["statistical_review_sha256"] == "df47de4ea92e4ecfb87ee19b6397c23ca11625745a798f83d57156eabf445604"
    assert current["qa_review_sha256"] == "79ba4c3fc004b317c799f5d4ff1edae13dad5828d32c9e0343ce3400dd03a262"
    assert current["allowed_years"] == [2019, 2020, 2021]
    assert current["locked_years"] == [2022, 2023]
    assert current["confirmation_unlocked"] is False
    assert current["phase_advanced"] is False
    assert current["strategy_authorized"] is False
    assert current["pnl_authorized"] is False
    assert current["execution_authorized"] is False
    assert current["live_authorized"] is False


def test_phase22b_runtime_termination_is_permanently_non_scientific():
    incident = load_json(ROOT / "governance/incidents/PH22B-RUNTIME-TERMINATION-001.json")
    assert incident["run_id"] == "phase22b_20260912T130732Z"
    assert incident["classification"] == "INVALID_FAILED_NON_SCIENTIFIC"
    assert incident["reason"] == "UNKNOWN_UNRECOVERABLE_RUNTIME_TERMINATION"
    assert incident["scientific_evidence_accepted"] is False
    assert incident["result_manifest_published"] is False
    assert incident["run_id_reusable"] is False
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    record = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22B_RUNTIME_TERMINATION_001")
    assert record["scientific_evidence_accepted"] is False
    assert record["run_id_reusable"] is False
    assert record["locked_windows"] == [2022, 2023]
    assert record["forbidden"] == "2024+"


def test_phase22b_dual_runtime_failure_reconciliation_is_fail_closed():
    first = load_json(ROOT / "governance/incidents/PH22B-DURABLE-RUNTIME-TERMINATION-004.json")
    second = load_json(ROOT / "governance/incidents/PH22B-DURABLE-LAUNCH-FAILURE-003.json")
    active = load_json(ROOT / "governance/state/phase22b_active_run.json")
    assert first["run_id"] == "phase22b_20260913T172656Z"
    assert second["run_id"] == "phase22b_20260913T172727Z"
    assert first["classification"] == second["classification"] == "INVALID_FAILED_NON_SCIENTIFIC"
    assert first["run_id_reusable"] is second["run_id_reusable"] is False
    assert first["supervisor_present_at_reconciliation"] is False
    assert first["worker_present_at_reconciliation"] is False
    assert active["state"] == "INVALID"
    assert active["scientific_status"] == "INVALID_FAILED_NON_SCIENTIFIC"
    assert active["next_authorized_action"] == "INDEPENDENT_QA_REVIEW_OF_PHASE22B_DURABLE_RUNTIME_REMEDIATION"