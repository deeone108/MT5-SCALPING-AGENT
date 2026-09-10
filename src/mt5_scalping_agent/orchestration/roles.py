from enum import Enum
from .errors import OrchestrationError, AUTHORITY_DENIED, HUMAN_GATE_REQUIRED

class Role(str, Enum):
    PROJECT_ORCHESTRATOR="project_orchestrator"; RESEARCH_LEAD="research_lead"
    DATA_ENGINEER="data_engineer"; RESEARCH_IMPLEMENTER="research_implementer"
    STATISTICAL_VALIDATOR="statistical_validator"; BACKTESTING_ENGINEER="backtesting_engineer"
    SAFETY_REVIEWER="safety_reviewer"; QA_REVIEWER="qa_reviewer"
    DOCUMENTATION_AGENT="documentation_agent"; HUMAN_OWNER="human_owner"

PERMISSIONS={
 Role.PROJECT_ORCHESTRATOR:{"ASSIGN","UNLOCK_DATA","ADVANCE_PHASE","ACCEPT_RESULT","CREATE_TASK"},
 Role.RESEARCH_LEAD:{"DESIGN","FREEZE_SPEC"}, Role.DATA_ENGINEER:{"MANAGE_DATA"},
 Role.RESEARCH_IMPLEMENTER:{"IMPLEMENT"}, Role.STATISTICAL_VALIDATOR:{"VALIDATE"},
 Role.BACKTESTING_ENGINEER:{"BACKTEST"}, Role.SAFETY_REVIEWER:{"SAFETY_REVIEW","VETO"},
 Role.QA_REVIEWER:{"QA_REVIEW","MERGE_RECOMMEND"}, Role.DOCUMENTATION_AGENT:{"DOCUMENT"},
 Role.HUMAN_OWNER:{"LIVE_ACTIVATE","HUMAN_APPROVE"}}
HUMAN_ONLY={"LIVE_ACTIVATE","WEAKEN_SAFETY_POLICY","CHANGE_HOLDOUT_POLICY","REPLACE_DATASET_AFTER_START","MUTATE_FROZEN_SPEC","DESTRUCTIVE_DATA_OPERATION","REWRITE_HISTORY"}

def require(role: str | Role, action: str) -> None:
    role=Role(role)
    if action in HUMAN_ONLY and role is not Role.HUMAN_OWNER:
        raise OrchestrationError(HUMAN_GATE_REQUIRED, f"{action} requires explicit human-owner approval")
    if action not in PERMISSIONS[role]:
        raise OrchestrationError(AUTHORITY_DENIED, f"{role.value} may not {action}")