"""Reproducible research-run metadata and checkpoint safeguards."""

from mt5_scalping_agent.research.manifest import (
    CheckpointCompatibilityError,
    ManifestError,
    build_run_manifest,
    checkpoint_document,
    fingerprint_dataframe,
    fingerprint_files,
    load_compatible_checkpoint,
    local_archive_dataset,
    sha256_value,
    strategy_descriptor,
    write_json_atomic,
)

__all__ = [
    "CheckpointCompatibilityError",
    "ManifestError",
    "build_run_manifest",
    "checkpoint_document",
    "fingerprint_dataframe",
    "fingerprint_files",
    "load_compatible_checkpoint",
    "local_archive_dataset",
    "sha256_value",
    "strategy_descriptor",
    "write_json_atomic",
]