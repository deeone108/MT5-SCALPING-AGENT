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