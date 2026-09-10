import json, re
from pathlib import Path
from typing import Any
from .errors import OrchestrationError, MANIFEST_INVALID
SHA40=re.compile(r"^[0-9a-f]{40}$"); SHA64=re.compile(r"^[0-9a-f]{64}$")

def load_json(path: str | Path) -> dict[str, Any]:
    try: value=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: raise OrchestrationError(MANIFEST_INVALID,str(e)) from e
    if not isinstance(value,dict): raise OrchestrationError(MANIFEST_INVALID,"manifest must be an object")
    return value

def require_fields(value: dict, fields: set[str], kind="manifest"):
    missing=fields-set(value)
    if missing: raise OrchestrationError(MANIFEST_INVALID,f"{kind} missing {sorted(missing)}")

def validate_hash(value: str | None, length=64, field="hash"):
    if value is None or not (SHA64 if length==64 else SHA40).fullmatch(value):
        raise OrchestrationError(MANIFEST_INVALID,f"invalid {field}")

def classify_test_outcome(returncode:int, stderr:str="", stdout:str="") -> str:
    if returncode==0: return "PASSED"
    text=(stderr+"\n"+stdout).lower()
    markers=("filenotfounderror","could not read registry evidence","external evidence")
    return "REQUIRED_EXTERNAL_EVIDENCE_MISSING" if any(x in text for x in markers) else "REGRESSION_FAILURE"
def validate_ledger(value: dict) -> dict:
    require_fields(value, {"schema_version", "current_phase", "live_execution_authorized", "decisions", "holdout_access_history", "rejected_hypothesis_families"}, "project ledger")
    if value["schema_version"] != 1 or value["live_execution_authorized"] is not False:
        raise OrchestrationError(MANIFEST_INVALID, "invalid ledger authority/version")
    required_ids = {"PHASE_22_DATASET", "PHASE_22A_COMPLETION"}
    if not required_ids <= {item.get("id") for item in value["decisions"]}:
        raise OrchestrationError(MANIFEST_INVALID, "ledger missing required project decisions")
    if any(item.get("accessed_2024_plus") is not False for item in value["holdout_access_history"]):
        raise OrchestrationError(MANIFEST_INVALID, "ledger records prohibited 2024+ access")
    return value