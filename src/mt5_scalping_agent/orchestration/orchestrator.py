from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from .gates import assert_data_access, validate_phase_advance, unlock_data_window
from .hashing import sha256_json
from .roles import require
from .state import StateStore
from .task import validate_task, transition
from .result import validate_result

class Orchestrator:
 def __init__(self,state_path): self.store=StateStore(state_path)
 def accept_task(self,task): require("project_orchestrator","CREATE_TASK"); validate_task(task); s=self.store.read(); assert_data_access(s,task,task["allowed_data_window"]); s["active_tasks"].append(task["task_id"]); self.store.write(s); return task
 def transition_task(self,task,status): return transition(task,status)
 def accept_result(self,result,task): require("project_orchestrator","ACCEPT_RESULT"); return validate_result(result,task,self.store.read())
 def unlock_window(self,window,evidence):
  s=unlock_data_window(self.store.read(),"project_orchestrator",window,evidence); self.store.write(s); return s
 def advance_phase(self,to_phase,evidence):
  s=self.store.read(); validate_phase_advance("project_orchestrator",s,evidence); old=s["phase_id"]; s["phase_id"]=to_phase; s["current_phase"]=to_phase; s["status"]="PROPOSED"; s["phase_status"]="PROPOSED"; record={"from":old,"to":to_phase,"authorized_by":"project_orchestrator","at_utc":datetime.now(timezone.utc).isoformat(),"evidence_sha256":sha256_json(evidence),"human_owner_approval_sha256":None}; s["transitions"].append(record); s["phase_transition_history"].append(record); self.store.write(s); return s