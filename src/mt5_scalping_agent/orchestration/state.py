import json, os, tempfile
from pathlib import Path
from typing import Any
from .validator import require_fields, validate_hash, load_json
from .errors import OrchestrationError, MANIFEST_INVALID
PHASE_STATUSES={"PROPOSED","DATA_PREPARATION","DESIGN_FROZEN","IMPLEMENTATION_REVIEW","DISCOVERY_RUNNING","DISCOVERY_FROZEN","CONFIRMATION_UNLOCKED","CONFIRMATION_RUNNING","CONFIRMATION_FROZEN","HOLDOUT_UNLOCKED","HOLDOUT_RUNNING","VALIDATION","COMPLETE","CLOSED","BLOCKED","INVALID"}
REQUIRED={"schema_version","phase_id","current_phase","status","phase_status","base_commit","orchestrator","research_spec_hash","dataset_root_hash","allowed_data_windows","locked_data_windows","forbidden_data_windows","active_tasks","completed_tasks","blocked_tasks","last_validated_commit","phase_transition_history","safety_state","live_execution_authorized","gates","data_access","transitions"}

def validate_state(v:dict)->dict:
    require_fields(v,REQUIRED,"phase state")
    if v["schema_version"]!=1 or v["orchestrator"]!="project_orchestrator": raise OrchestrationError(MANIFEST_INVALID,"invalid state authority/version")
    if v["status"] not in PHASE_STATUSES or v["phase_status"]!=v["status"]: raise OrchestrationError(MANIFEST_INVALID,"invalid/inconsistent phase status")
    validate_hash(v["base_commit"],40,"base_commit"); validate_hash(v["last_validated_commit"],40,"last_validated_commit")
    validate_hash(v["research_spec_hash"],64,"research_spec_hash"); validate_hash(v["dataset_root_hash"],64,"dataset_root_hash")
    if v["live_execution_authorized"] is not False: raise OrchestrationError(MANIFEST_INVALID,"LIVE must remain unauthorized")
    return v

class StateStore:
    def __init__(self,path:str|Path): self.path=Path(path)
    def read(self): return validate_state(load_json(self.path))
    def write(self,value:dict):
        validate_state(value); self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f: json.dump(value,f,indent=2,sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)