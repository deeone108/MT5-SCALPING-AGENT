"""Regression checks for the immutable, selected XAU-60 source snapshot."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN = "b877fdb1fcc5888b1443cf0214ea89f8040e8096"
PREFIX = f"third_party/xau60/{PIN}"
SOURCE_PREFIX = f"{PREFIX}/source/"
MANIFEST_PATH = ROOT / "reports" / "bot_xau60_source_manifest.json"


def _git_blob(relative_path: str) -> bytes:
    return subprocess.check_output(
        ["git", "cat-file", "blob", f"HEAD:{relative_path}"], cwd=ROOT
    )


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_all_selected_files_match_immutable_git_blobs_and_checkout() -> None:
    manifest = _manifest()
    files = manifest["snapshot"]["files"]
    assert len(files) == manifest["snapshot"]["file_count"] == 13
    assert len({item["path"] for item in files}) == 13

    for item in files:
        relative = SOURCE_PREFIX + item["path"]
        blob = _git_blob(relative)
        assert len(blob) == item["size_bytes"]
        assert hashlib.sha256(blob).hexdigest() == item["sha256"]
        assert (ROOT / relative).read_bytes() == blob


def test_aggregate_license_pin_and_checkout_policy_reproduce() -> None:
    manifest = _manifest()
    records = sorted(
        (item["path"], item["sha256"], item["size_bytes"])
        for item in manifest["snapshot"]["files"]
    )
    aggregate_bytes = "".join(
        f"{path}\0{digest}\0{size}\n" for path, digest, size in records
    ).encode("utf-8")
    assert hashlib.sha256(aggregate_bytes).hexdigest() == manifest["snapshot"]["sha256"]

    license_item = next(item for item in manifest["snapshot"]["files"] if item["path"] == "LICENSE")
    assert manifest["license"]["sha256"] == license_item["sha256"]
    assert manifest["pinned_commit"] == PIN
    assert f"Pinned commit: {PIN}" in (ROOT / PREFIX / "THIRD_PARTY_SOURCE").read_text(encoding="utf-8")
    assert (ROOT / PREFIX / ".gitattributes").read_text(encoding="utf-8").strip() == "source/** -text"


def test_integrity_correction_preserves_original_claim_and_payload() -> None:
    correction = _manifest()["integrity_correction"]
    assert correction == {
        "incident_id": "BOT-03-XAU60-SNAPSHOT-INTEGRITY-001",
        "original_declared_snapshot_sha256": "9da0c41f95f99da967c3bc543b370b0513c95529ee97eb70731768291223f7f0",
        "original_hash_basis": "CRLF working-tree bytes",
        "corrected_hash_basis": "immutable Git blob bytes",
        "source_payload_changed": False,
        "source_logic_changed": False,
    }
