from .errors import OrchestrationError, RESULT_REJECTED, MANIFEST_INVALID
from .validator import require_fields, validate_hash
from .hashing import sha256_file
from pathlib import Path
REQUIRED={"schema_version","task_id","role","start_time","end_time","status","base_commit","result_commit","files_changed","artifacts","artifact_hashes","tests_executed","test_results","data_windows_accessed","specification_hash_used","dataset_hash_used","safety_checks","review_status","terminal_result","inputs","commands","tests","data_accessed","prohibitions_verified","handoff"}

def validate_result(v:dict,task:dict,state:dict)->dict:
    require_fields(v,REQUIRED,"result")
    if v["task_id"]!=task["task_id"] or v["role"]!=task["assigned_role"]: raise OrchestrationError(MANIFEST_INVALID,"task/role mismatch")
    validate_hash(v["base_commit"],40,"base_commit"); validate_hash(v["result_commit"],40,"result_commit")
    if v["base_commit"]!=task["base_commit"]: raise OrchestrationError(RESULT_REJECTED,"base commit changed")
    if v["specification_hash_used"]!=task["required_spec_hash"]: raise OrchestrationError(RESULT_REJECTED,"wrong specification hash")
    if v["dataset_hash_used"]!=task["required_dataset_hash"]: raise OrchestrationError(RESULT_REJECTED,"wrong dataset hash")
    if not set(v["data_windows_accessed"])<=set(task["allowed_data_window"]): raise OrchestrationError(RESULT_REJECTED,"unauthorized data accessed")
    names={x.get("name") for x in v["test_results"] if x.get("status")=="PASSED"}
    if not set(task["required_tests"])<=names: raise OrchestrationError(RESULT_REJECTED,"required tests absent or failed")
    approvals={x.get("role") for x in v["review_status"] if x.get("decision")=="APPROVED"}
    if not set(task["required_reviewers"])<=approvals: raise OrchestrationError(RESULT_REJECTED,"required reviewer approval absent")
    if any(x.get("status") not in {"PASSED","NOT_REQUIRED"} for x in v["safety_checks"]): raise OrchestrationError(RESULT_REJECTED,"safety gate failed")
    if not v["terminal_result"]: raise OrchestrationError(RESULT_REJECTED,"terminal result absent")
    return v
PHASE22B_EVIDENCE_REQUIRED={"schema_version","candidate_id","specification_hash","code_version","dataset_authorization_id","research_run_id","actionable","strategy_eligible","trade_direction","primary_raw_pip_effect","normalized_diagnostic_effect","confidence_intervals","raw_p_values","adjusted_p_values","fdr_decisions","temporal_replication_results","pair_stability","concentration_diagnostics","session_diagnostics","regime_diagnostics","missingness","limitations","terminal_scientific_classification","reviewer_verdicts","reviewer_artifact_hashes","provenance_hashes"}

def validate_phase22b_evidence(v:dict)->dict:
    require_fields(v,PHASE22B_EVIDENCE_REQUIRED,"phase22b evidence")
    if v["schema_version"]!=1 or v["candidate_id"]!="P22A_SPR_ABS_15s_60s":
        raise OrchestrationError(MANIFEST_INVALID,"wrong Phase 22B evidence identity")
    validate_hash(v["specification_hash"],64,"specification_hash")
    validate_hash(v["code_version"],40,"code_version")
    if v["actionable"] is not False or v["strategy_eligible"] is not False or v["trade_direction"] is not None:
        raise OrchestrationError(RESULT_REJECTED,"Phase 22B evidence must remain non-actionable")
    if set(v["reviewer_verdicts"])!={"statistical_validator","qa_reviewer"}:
        raise OrchestrationError(MANIFEST_INVALID,"independent reviewer verdicts required")
    return v
def verify_artifact_hashes(v:dict, project_root:str|Path)->dict:
    """Reproduce declared hashes from artifact contents; never trust manifest strings."""
    root=Path(project_root).resolve()
    for artifact in v.get("artifacts",[]):
        target=(root/artifact["path"]).resolve()
        if root not in target.parents or not target.is_file():
            raise OrchestrationError(RESULT_REJECTED,"artifact path missing or outside project root")
        actual=sha256_file(target)
        if actual!=artifact["sha256"] or v.get("artifact_hashes",{}).get(artifact["path"])!=actual:
            raise OrchestrationError(RESULT_REJECTED,"artifact content hash mismatch")
    return v