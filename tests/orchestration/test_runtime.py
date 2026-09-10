import json, subprocess
from copy import deepcopy
from pathlib import Path
import pytest
from mt5_scalping_agent.orchestration.errors import OrchestrationError
from mt5_scalping_agent.orchestration.freeze import freeze_experiment
from mt5_scalping_agent.orchestration.gates import assert_data_access, assert_no_methodology_change, unlock_data_window, validate_phase_advance, verify_frozen_spec
from mt5_scalping_agent.orchestration.hashing import sha256_file
from mt5_scalping_agent.orchestration.orchestrator import Orchestrator
from mt5_scalping_agent.orchestration.result import validate_result
from mt5_scalping_agent.orchestration.roles import require
from mt5_scalping_agent.orchestration.state import StateStore
from mt5_scalping_agent.orchestration.task import transition, recover_interrupted
from mt5_scalping_agent.orchestration.validator import classify_test_outcome
from mt5_scalping_agent.orchestration.worktree import assert_worker_worktree, create, inspect

H40="a"*40; SPEC="b"*64; DATA="c"*64

def state():
 return {"schema_version":1,"phase_id":"FAKE_A","current_phase":"FAKE_A","status":"DISCOVERY_RUNNING","phase_status":"DISCOVERY_RUNNING","base_commit":H40,"orchestrator":"project_orchestrator","research_spec_hash":SPEC,"spec_sha256":SPEC,"dataset_root_hash":DATA,"allowed_data_windows":["2019","2020","2021"],"locked_data_windows":["2022","2023"],"forbidden_data_windows":["2024+"],"active_tasks":[],"completed_tasks":[],"blocked_tasks":[],"candidate_registry_hash":None,"last_validated_commit":H40,"phase_transition_history":[],"safety_state":{"status":"ENFORCED","order_submission":False},"live_execution_authorized":False,"gates":{k:{"status":"PASSED" if k in {"data","freeze","safety"} else "PENDING","reviewer_role":"qa_reviewer","evidence_sha256":None} for k in ("data","freeze","implementation","statistics","qa","safety")},"data_access":{"allowed_partitions":["2019","2020","2021"],"locked_partitions":["2022","2023","2024+"],"unlock_manifest_sha256":None},"transitions":[]}

def task():
 return {"schema_version":1,"task_id":"FAKE-001","phase":"FAKE_A","phase_id":"FAKE_A","assigned_role":"research_implementer","objective":"synthetic implementation","inputs":[],"allowed_paths":["synthetic/"],"forbidden_paths":["main/","research/frozen.json"],"allowed_data_window":["2019"],"required_spec_hash":SPEC,"required_dataset_hash":DATA,"base_commit":H40,"branch":"task/fake","worktree":"/tmp/fake","required_tests":["synthetic_test"],"required_reviewers":["statistical_validator","qa_reviewer"],"completion_conditions":["artifact"],"status":"CREATED","allowed_data":[{"root_sha256":DATA,"partitions":["2019"]}],"prohibited_actions":["LIVE"],"required_outputs":["result manifest"]}

def result():
 return {"schema_version":1,"task_id":"FAKE-001","role":"research_implementer","start_time":"2026-01-01T00:00:00Z","end_time":"2026-01-01T00:01:00Z","status":"COMPLETE","base_commit":H40,"result_commit":"d"*40,"files_changed":["synthetic/output.txt"],"artifacts":[],"artifact_hashes":{},"tests_executed":["synthetic_test"],"test_results":[{"name":"synthetic_test","status":"PASSED"}],"data_windows_accessed":["2019"],"specification_hash_used":SPEC,"dataset_hash_used":DATA,"safety_checks":[{"name":"no_live","status":"PASSED"}],"review_status":[{"role":"statistical_validator","decision":"APPROVED"},{"role":"qa_reviewer","decision":"APPROVED"}],"terminal_result":"SYNTHETIC_COMPLETE","inputs":[],"commands":[],"tests":[],"data_accessed":["2019"],"prohibitions_verified":["LIVE"],"handoff":{"to_role":"project_orchestrator","requested_decision":"accept","limitations":[]}}

def full_evidence(): return {k:True for k in ("discovery_complete","survivor_registry_frozen","confirmation_complete","holdout_complete","statistical_validation_approved","leakage_validation_approved","qa_approved","result_manifest_accepted","tests_passed","phase_completion_artifact")}

def rejected(call,code):
 with pytest.raises(OrchestrationError) as e: call()
 assert e.value.code==code

def test_adversarial_authority_and_methodology_rejections():
 freeze={"specification_path":"research/frozen.json"}
 rejected(lambda: assert_no_methodology_change("research_implementer",["research/frozen.json"],freeze),"AUTHORITY_DENIED")
 rejected(lambda: assert_no_methodology_change("statistical_validator",["research/frozen.json"],freeze),"AUTHORITY_DENIED")
 rejected(lambda: require("qa_reviewer","ADVANCE_PHASE"),"AUTHORITY_DENIED")
 rejected(lambda: require("research_implementer","UNLOCK_DATA"),"AUTHORITY_DENIED")
 rejected(lambda: require("project_orchestrator","LIVE_ACTIVATE"),"HUMAN_GATE_REQUIRED")
 rejected(lambda: require("safety_reviewer","WEAKEN_SAFETY_POLICY"),"HUMAN_GATE_REQUIRED")

def test_adversarial_data_access_rejections():
 rejected(lambda: assert_data_access(state(),task(),["2022"]),"DATA_ACCESS_GATE_DENIED")
 rejected(lambda: assert_data_access(state(),task(),["2024+"]),"DATA_ACCESS_GATE_DENIED")

def test_result_rejects_hash_test_review_and_safety_bypass():
 for mutate in (
  lambda r:r.update(specification_hash_used="e"*64), lambda r:r.update(dataset_hash_used="e"*64),
  lambda r:r.update(test_results=[]), lambda r:r.update(review_status=[]),
  lambda r:r.update(safety_checks=[{"name":"execution","status":"VETOED"}]),
  lambda r:r.update(data_windows_accessed=["2022"])):
  r=result(); mutate(r); rejected(lambda r=r:validate_result(r,task(),state()),"RESULT_REJECTED")

def test_invalid_task_jump_and_interruption_recovery():
 rejected(lambda:transition(task(),"COMPLETED"),"INVALID_TRANSITION")
 t=task(); t["status"]="RUNNING"; assert recover_interrupted(t,False)["status"]=="UNVERIFIED_INTERRUPTED"; assert recover_interrupted(t,True)["status"]=="RUNNING"

def test_phase_advance_requires_complete_qa_and_honors_safety_veto():
 evidence=full_evidence(); evidence["qa_approved"]=False
 rejected(lambda:validate_phase_advance("project_orchestrator",state(),evidence),"RESULT_REJECTED")
 s=state(); s["gates"]["safety"]["status"]="VETOED"
 rejected(lambda:validate_phase_advance("project_orchestrator",s,full_evidence()),"RESULT_REJECTED")

def test_freeze_is_hash_bound(tmp_path):
 spec=tmp_path/"spec.json"; spec.write_text('{"candidate":"fake"}\n')
 f=freeze_experiment(role="research_lead",specification_path="spec.json",project_root=tmp_path,dataset_root=DATA,git_commit=H40,phase="FAKE_A",allowed_data=["2019"],random_seeds=[1],methodology_version="v1")
 t=task(); t["required_spec_hash"]=f["sha256"]; verify_frozen_spec(f,t,tmp_path)
 spec.write_text('{"candidate":"changed"}\n'); rejected(lambda:verify_frozen_spec(f,t,tmp_path),"RESULT_REJECTED")

def test_worker_cannot_use_main_and_task_worktree_is_isolated(tmp_path):
 repo=tmp_path/"repo"; repo.mkdir(); subprocess.run(["git","init","-b","main"],cwd=repo,check=True,capture_output=True); subprocess.run(["git","config","user.email","test@example.invalid"],cwd=repo,check=True); subprocess.run(["git","config","user.name","Test"],cwd=repo,check=True); (repo/"x").write_text("x"); subprocess.run(["git","add","x"],cwd=repo,check=True); subprocess.run(["git","commit","-m","base"],cwd=repo,check=True,capture_output=True)
 rejected(lambda:assert_worker_worktree(repo),"WORKTREE_POLICY_DENIED")
 wt=tmp_path/"worker"; info=create(repo,wt,"task/fake","HEAD"); assert info["branch"]=="task/fake" and not info["is_main"]

def test_synthetic_multi_agent_success_and_fail_closed(tmp_path):
 p=tmp_path/"state.json"; StateStore(p).write(state()); orch=Orchestrator(p); t=task(); orch.accept_task(t)
 for status in ("READY","RUNNING","IMPLEMENTED","VALIDATING","REVIEWING","APPROVED","COMPLETED"): t=orch.transition_task(t,status)
 assert orch.accept_result(result(),task())["terminal_result"]=="SYNTHETIC_COMPLETE"
 advanced=orch.advance_phase("FAKE_B",full_evidence()); assert advanced["current_phase"]=="FAKE_B"
 r=result(); r["specification_hash_used"]="0"*64; rejected(lambda:validate_result(r,task(),state()),"RESULT_REJECTED")
 rejected(lambda:assert_data_access(state(),task(),["2022"]),"DATA_ACCESS_GATE_DENIED")
 rejected(lambda:require("project_orchestrator","LIVE_ACTIVATE"),"HUMAN_GATE_REQUIRED")

def test_evidence_aware_test_classification_is_not_greenwashing():
 assert classify_test_outcome(1,stdout="FileNotFoundError: reports/chronological_validation/x.json")=="REQUIRED_EXTERNAL_EVIDENCE_MISSING"
 assert classify_test_outcome(1,stdout="AssertionError")=="REGRESSION_FAILURE"
 assert classify_test_outcome(0)=="PASSED"
def test_staged_unlock_requires_freeze_and_survivor_hash():
 s=state()
 rejected(lambda:unlock_data_window(s,"project_orchestrator","2022",{}),"DATA_ACCESS_GATE_DENIED")
 s["status"]="DISCOVERY_FROZEN"; s["phase_status"]="DISCOVERY_FROZEN"
 unlocked=unlock_data_window(s,"project_orchestrator","2022",{"discovery_survivor_hash":"f"*64})
 assert "2022" in unlocked["allowed_data_windows"] and unlocked["status"]=="CONFIRMATION_UNLOCKED"
 rejected(lambda:unlock_data_window(s,"research_implementer","2022",{"discovery_survivor_hash":"f"*64}),"AUTHORITY_DENIED")
 rejected(lambda:unlock_data_window(s,"project_orchestrator","2024+",{}),"HUMAN_GATE_REQUIRED")