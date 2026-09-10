from pathlib import Path
from .errors import OrchestrationError, DATA_ACCESS_GATE_DENIED, RESULT_REJECTED, HUMAN_GATE_REQUIRED, AUTHORITY_DENIED
from .hashing import sha256_canonical_text_file
from .roles import Role, require

def assert_data_access(state:dict,task:dict,requested:list[str|int]):
    allowed={str(x) for x in state["allowed_data_windows"]}&{str(x) for x in task["allowed_data_window"]}
    locked={str(x) for x in state["locked_data_windows"]}; forbidden={str(x) for x in state["forbidden_data_windows"]}
    denied={str(x) for x in requested}-allowed
    if denied or ({str(x) for x in requested}&(locked|forbidden)):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED,f"denied windows {sorted(denied or ({str(x) for x in requested}&(locked|forbidden)))}")

def unlock_data_window(state:dict,role:str,window:str,evidence:dict)->dict:
    from copy import deepcopy
    require(role,"UNLOCK_DATA")
    window=str(window)
    if window=="2024+" or window.startswith("2024"):
        raise OrchestrationError(HUMAN_GATE_REQUIRED,"2024+ remains prohibited")
    prerequisites={"2022":("DISCOVERY_FROZEN","discovery_survivor_hash"),"2023":("CONFIRMATION_FROZEN","confirmation_survivor_hash")}
    if window not in prerequisites: raise OrchestrationError(DATA_ACCESS_GATE_DENIED,f"unsupported unlock {window}")
    required_status,hash_field=prerequisites[window]
    if state["status"]!=required_status or not evidence.get(hash_field):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED,f"{window} unlock requires {required_status} and {hash_field}")
    out=deepcopy(state)
    if window not in out["locked_data_windows"]: raise OrchestrationError(DATA_ACCESS_GATE_DENIED,f"{window} is not locked")
    out["locked_data_windows"].remove(window); out["allowed_data_windows"].append(window)
    out["data_access"]["locked_partitions"].remove(window); out["data_access"]["allowed_partitions"].append(window)
    out["status"]="CONFIRMATION_UNLOCKED" if window=="2022" else "HOLDOUT_UNLOCKED"; out["phase_status"]=out["status"]
    return out
def verify_frozen_spec(freeze:dict,task:dict,project_root:Path):
    actual=sha256_canonical_text_file(project_root/freeze["specification_path"])
    if actual!=freeze["sha256"] or actual!=task["required_spec_hash"]: raise OrchestrationError(RESULT_REJECTED,"frozen specification hash changed")
    if freeze["dataset_root"]!=task["required_dataset_hash"]: raise OrchestrationError(RESULT_REJECTED,"dataset root changed")

def assert_no_methodology_change(role:str,changed_paths:list[str],freeze:dict):
    if freeze["specification_path"] in changed_paths and role in {Role.RESEARCH_IMPLEMENTER.value,Role.STATISTICAL_VALIDATOR.value,Role.PROJECT_ORCHESTRATOR.value}:
        raise OrchestrationError(AUTHORITY_DENIED,"role may not mutate frozen specification")

def validate_phase_advance(role:str,state:dict,evidence:dict):
    require(role,"ADVANCE_PHASE")
    needed={"discovery_complete","survivor_registry_frozen","confirmation_complete","holdout_complete","statistical_validation_approved","leakage_validation_approved","qa_approved","result_manifest_accepted","tests_passed","phase_completion_artifact"}
    missing=sorted(k for k in needed if evidence.get(k) is not True)
    if missing: raise OrchestrationError(RESULT_REJECTED,f"phase evidence incomplete: {missing}")
    if state["gates"]["safety"]["status"] in {"FAILED","VETOED"}: raise OrchestrationError(RESULT_REJECTED,"safety gate failed")
    if evidence.get("live_activation"): raise OrchestrationError(HUMAN_GATE_REQUIRED,"LIVE activation is never an agent phase transition")