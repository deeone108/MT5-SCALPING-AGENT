"""Fail-closed, resumable remediation-loop controls.

This module manages governance evidence only.  It never opens research data or
changes a frozen research specification.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Iterable

from .errors import HUMAN_GATE_REQUIRED, MANIFEST_INVALID, OrchestrationError
from .validator import require_fields, validate_hash

AGENT_RESOLVABLE = "AGENT_RESOLVABLE"
HUMAN_REQUIRED = "HUMAN_GATE_REQUIRED"
CLASSIFICATIONS = {AGENT_RESOLVABLE, HUMAN_REQUIRED}
STATES = {"REVIEW_REJECTED", "REMEDIATION_READY", "REMEDIATION_RUNNING", "PENDING_INDEPENDENT_REVIEW", "HUMAN_GATE_REQUIRED", "CLOSED"}
HARD_STOP_CODES = {"DATA_2024_PLUS", "LIVE_ACTIVATION", "SCOPE_CHANGE", "REVIEW_BYPASS", "FROZEN_ARTIFACT_MUTATION", "OWNER_DECISION_REQUIRED"}
REQUIRED = {"schema_version", "loop_id", "phase", "candidate_id", "state", "lineage", "attempts", "current_spec_hash", "review_artifacts", "finding_fingerprints", "next_transition", "safety"}


def finding_fingerprint(finding: dict) -> str:
    """Stable identity independent of prose order or timestamps."""
    material = {
        "code": finding.get("code"),
        "severity": finding.get("severity"),
        "affected_contract": finding.get("affected_contract"),
        "required_correction": finding.get("required_correction"),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classify_findings(findings: Iterable[dict]) -> str:
    """Return HUMAN_GATE_REQUIRED for any authority/safety boundary crossing."""
    items = list(findings)
    if not items:
        raise OrchestrationError(MANIFEST_INVALID, "review rejection has no findings")
    for item in items:
        if item.get("code") in HARD_STOP_CODES or item.get("requires_human_authority") is True:
            return HUMAN_REQUIRED
        if item.get("agent_resolvable") is not True:
            return HUMAN_REQUIRED
    return AGENT_RESOLVABLE


def make_remediation_descriptor(loop: dict, findings: list[dict], *, task_id: str, assigned_role: str) -> dict:
    """Create a bounded no-data descriptor while preserving review evidence."""
    validate_loop(loop)
    classification = classify_findings(findings)
    fingerprints = sorted(finding_fingerprint(x) for x in findings)
    return {
        "schema_version": 1,
        "task_id": task_id,
        "loop_id": loop["loop_id"],
        "assigned_role": assigned_role,
        "classification": classification,
        "source_spec_hash": loop["current_spec_hash"],
        "source_reviews": deepcopy(loop["review_artifacts"]),
        "finding_fingerprints": fingerprints,
        "allowed_data_window": [],
        "prohibited_actions": ["ACCESS_MARKET_DATA", "ACCESS_2024_PLUS", "CHANGE_SCOPE", "BYPASS_REVIEW", "ENABLE_LIVE", "MUTATE_FROZEN_SPEC"],
        "required_outputs": ["superseding_specification", "canonical_sha256", "result_manifest", "independent_review_request"],
        "next_transition": "HUMAN_GATE_REQUIRED" if classification == HUMAN_REQUIRED else "REMEDIATION_RUNNING",
    }


def detect_deadlock(loop: dict, *, proposed_spec_hash: str, finding_fingerprints: Iterable[str], material_change: bool) -> bool:
    """Detect repeated non-progress; no arbitrary retry count is used."""
    validate_loop(loop)
    validate_hash(proposed_spec_hash, 64, "proposed_spec_hash")
    fingerprints = sorted(finding_fingerprints)
    for attempt in loop["attempts"]:
        same_findings = sorted(attempt["finding_fingerprints"]) == fingerprints
        same_hash = attempt["output_spec_hash"] == proposed_spec_hash
        if same_findings and (same_hash or not material_change or not attempt["material_change"]):
            return True
    return False


def record_attempt(loop: dict, *, descriptor: dict, output_spec_hash: str, material_change: bool) -> dict:
    """Persist an attempt or fail closed when evidence shows no progress."""
    validate_loop(loop)
    if descriptor["classification"] == HUMAN_REQUIRED:
        out = deepcopy(loop); out["state"] = HUMAN_REQUIRED; out["next_transition"] = "HUMAN_OWNER_DECISION"
        return out
    fps = descriptor["finding_fingerprints"]
    if detect_deadlock(loop, proposed_spec_hash=output_spec_hash, finding_fingerprints=fps, material_change=material_change):
        out = deepcopy(loop); out["state"] = HUMAN_REQUIRED; out["next_transition"] = "HUMAN_OWNER_DEADLOCK_RESOLUTION"
        return out
    out = deepcopy(loop)
    out["attempts"].append({"task_id": descriptor["task_id"], "input_spec_hash": loop["current_spec_hash"], "output_spec_hash": output_spec_hash, "finding_fingerprints": fps, "material_change": material_change})
    out["lineage"].append({"from_spec_hash": loop["current_spec_hash"], "to_spec_hash": output_spec_hash, "task_id": descriptor["task_id"]})
    out["current_spec_hash"] = output_spec_hash
    out["finding_fingerprints"] = fps
    out["state"] = "PENDING_INDEPENDENT_REVIEW"
    out["next_transition"] = "INDEPENDENT_STATISTICAL_AND_QA_REVIEW"
    return validate_loop(out)


def validate_loop(value: dict) -> dict:
    require_fields(value, REQUIRED, "remediation loop")
    if value["schema_version"] != 1 or value["state"] not in STATES:
        raise OrchestrationError(MANIFEST_INVALID, "invalid remediation loop version/state")
    validate_hash(value["current_spec_hash"], 64, "current_spec_hash")
    safety = value["safety"]
    if safety != {"allowed_data_window": [], "live_execution_authorized": False, "review_bypass_authorized": False, "scope_change_authorized": False}:
        raise OrchestrationError(HUMAN_GATE_REQUIRED, "remediation safety boundary changed")
    for review in value["review_artifacts"]:
        validate_hash(review["sha256"], 64, "review sha256")
    return value
