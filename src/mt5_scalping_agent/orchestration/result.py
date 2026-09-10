from .errors import OrchestrationError, RESULT_REJECTED, MANIFEST_INVALID
from .validator import require_fields, validate_hash
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