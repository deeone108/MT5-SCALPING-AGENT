from copy import deepcopy
from .errors import OrchestrationError, INVALID_TRANSITION, MANIFEST_INVALID
from .validator import require_fields, validate_hash
from .roles import Role
STATUSES={"CREATED","READY","RUNNING","UNVERIFIED_INTERRUPTED","BLOCKED","IMPLEMENTED","VALIDATING","REVIEWING","APPROVED","REJECTED","COMPLETED"}
TRANSITIONS={"CREATED":{"READY","BLOCKED"},"READY":{"RUNNING","BLOCKED"},"RUNNING":{"IMPLEMENTED","BLOCKED","UNVERIFIED_INTERRUPTED"},"UNVERIFIED_INTERRUPTED":{"READY","BLOCKED","REJECTED"},"BLOCKED":{"READY","REJECTED"},"IMPLEMENTED":{"VALIDATING","REJECTED"},"VALIDATING":{"REVIEWING","REJECTED"},"REVIEWING":{"APPROVED","REJECTED"},"APPROVED":{"COMPLETED"},"REJECTED":set(),"COMPLETED":set()}
REQUIRED={"schema_version","task_id","phase","phase_id","assigned_role","objective","inputs","allowed_paths","forbidden_paths","allowed_data_window","required_spec_hash","required_dataset_hash","base_commit","branch","worktree","required_tests","required_reviewers","completion_conditions","status","allowed_data","prohibited_actions","required_outputs"}

def validate_task(v:dict)->dict:
    require_fields(v,REQUIRED,"task")
    if v["schema_version"]!=1 or v["status"] not in STATUSES: raise OrchestrationError(MANIFEST_INVALID,"bad task version/status")
    Role(v["assigned_role"]); validate_hash(v["base_commit"],40,"base_commit"); validate_hash(v["required_spec_hash"],64,"required_spec_hash"); validate_hash(v["required_dataset_hash"],64,"required_dataset_hash")
    if not v["required_tests"] or not v["required_reviewers"] or "qa_reviewer" not in v["required_reviewers"]: raise OrchestrationError(MANIFEST_INVALID,"tests and independent QA required")
    return v

def transition(v:dict,to_status:str)->dict:
    validate_task(v)
    if to_status not in TRANSITIONS[v["status"]]: raise OrchestrationError(INVALID_TRANSITION,f"{v['status']} -> {to_status}")
    out=deepcopy(v); out["status"]=to_status; return out

def recover_interrupted(v:dict,process_evidence:bool)->dict:
    if v["status"]!="RUNNING": return v
    return v if process_evidence else transition(v,"UNVERIFIED_INTERRUPTED")