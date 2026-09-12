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
    assert state["active_tasks"] == ["PH22B-RI-002"]
    assert state["status"] == "IMPLEMENTATION_REVIEW"
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
