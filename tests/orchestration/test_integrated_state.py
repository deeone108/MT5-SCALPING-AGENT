from pathlib import Path
from mt5_scalping_agent.orchestration.state import StateStore
from mt5_scalping_agent.orchestration.validator import load_json, validate_ledger
ROOT = Path(__file__).resolve().parents[2]
def test_integrated_project_state_is_valid_and_fail_closed():
    state = StateStore(ROOT / "governance/state/project_state.json").read()
    assert state["current_phase"] == "PHASE_22B_PENDING_DESIGN"
    assert state["live_execution_authorized"] is False
    assert state["allowed_data_windows"] == []
    assert state["forbidden_data_windows"] == ["2024+"]
def test_integrated_ledger_records_accepted_phase22a():
    ledger = validate_ledger(load_json(ROOT / "governance/memory/project_ledger.json"))
    completion = next(x for x in ledger["decisions"] if x["id"] == "PHASE_22A_COMPLETION")
    assert completion["final_report_sha256"] == "05910f453b7ccff64748fe90ff35b3195ccb1c5fa5653f21cd954a8a4112ee4a"
    assert completion["concentration_qualified"] == 22
    assert completion["accessed_2024_plus"] is False