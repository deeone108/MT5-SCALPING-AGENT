import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "governance"
ROLES = {
    "orchestrator.md", "research_lead.md", "data_engineer.md",
    "research_implementer.md", "statistical_validator.md",
    "backtest_engineer.md", "safety_reviewer.md", "qa_reviewer.md",
    "documentation_agent.md",
}


def resolve_ref(root: dict, reference: str) -> dict:
    value = root
    for part in reference.removeprefix("#/").split("/"):
        value = value[part]
    return value


def validate(instance, schema: dict, root: dict) -> None:
    if "$ref" in schema:
        validate(instance, resolve_ref(root, schema["$ref"]), root)
        return
    expected = schema.get("type")
    if expected:
        choices = expected if isinstance(expected, list) else [expected]
        matches = {
            "object": isinstance(instance, dict),
            "array": isinstance(instance, list),
            "string": isinstance(instance, str),
            "null": instance is None,
            "integer": isinstance(instance, int) and not isinstance(instance, bool),
            "boolean": isinstance(instance, bool),
        }
        if not any(matches.get(choice, False) for choice in choices):
            raise ValueError(f"type mismatch: expected {choices}")
    if "const" in schema and instance != schema["const"]:
        raise ValueError("const mismatch")
    if "enum" in schema and instance not in schema["enum"]:
        raise ValueError("enum mismatch")
    if isinstance(instance, str) and "pattern" in schema and not re.fullmatch(schema["pattern"], instance):
        raise ValueError("pattern mismatch")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                raise ValueError(f"missing {key}")
        properties = schema.get("properties", {})
        extra_rule = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], root)
            elif extra_rule is False:
                raise ValueError(f"unexpected {key}")
            elif isinstance(extra_rule, dict):
                validate(value, extra_rule, root)
    if isinstance(instance, list) and "items" in schema:
        for value in instance:
            validate(value, schema["items"], root)


@pytest.mark.parametrize(
    ("schema_name", "example_name"),
    [
        ("PHASE_STATE.schema.json", "phase_state.example.json"),
        ("TASK_MANIFEST.schema.json", "task_manifest.example.json"),
        ("RESULT_MANIFEST.schema.json", "result_manifest.example.json"),
    ],
)
def test_examples_conform_to_machine_readable_schemas(schema_name: str, example_name: str) -> None:
    schema = json.loads((GOVERNANCE / schema_name).read_text(encoding="utf-8"))
    example = json.loads((GOVERNANCE / "examples" / example_name).read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validate(example, schema, schema)


def test_only_orchestrator_can_authorize_phase_transition() -> None:
    schema = json.loads((GOVERNANCE / "PHASE_STATE.schema.json").read_text(encoding="utf-8"))
    state = json.loads((GOVERNANCE / "examples" / "phase_state.example.json").read_text(encoding="utf-8"))
    state["transitions"] = [{
        "from": "DESIGN_FROZEN",
        "to": "DISCOVERY_RUNNING",
        "authorized_by": "research_lead",
        "at_utc": "2026-09-10T00:00:00Z",
        "evidence_sha256": "a" * 64,
    }]
    with pytest.raises(ValueError, match="const"):
        validate(state, schema, schema)


def test_all_role_charters_define_complete_authority_contracts() -> None:
    assert {path.name for path in (ROOT / "agents").glob("*.md")} == ROLES
    sections = (
        "Responsibilities", "Allowed actions", "Prohibited actions",
        "Required inputs", "Required outputs", "Handoff contract",
        "Escalation conditions", "Merge authority", "Phase advancement authority",
    )
    for name in ROLES:
        text = (ROOT / "agents" / name).read_text(encoding="utf-8")
        assert all(f"## {section}" in text for section in sections)


def test_constitution_preserves_phase22a_freeze_and_universal_safety() -> None:
    canonical_spec = subprocess.check_output(
        ["git", "show", "d7c79e40d98316bf957f0e7428d464b959b0206a:research/phase22a_spec.json"],
        cwd=ROOT,
    )
    assert hashlib.sha256(canonical_spec).hexdigest() == "11581b33dcd0616d25ad39cc2de37db6e4bbba62e49ea1d283b1a3449d988323"
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "AGENTS.md", *sorted(GOVERNANCE.glob("*.md"))]
    )
    required = (
        "Only the Project Orchestrator", "explicit human-owner approval",
        "Safety Reviewer", "veto", "holdout", "frozen",
        "No automatic merge to main",
    )
    assert all(term.lower() in combined.lower() for term in required)
