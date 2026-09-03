"""Canonical manifests for reproducible, safely resumable research runs."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

MANIFEST_SCHEMA_VERSION = 1
CHECKPOINT_SCHEMA_VERSION = 2


class ManifestError(RuntimeError):
    """Raised when reproducible run metadata cannot be constructed or read."""


class CheckpointCompatibilityError(ManifestError):
    """Raised when a checkpoint cannot safely be resumed for the requested run."""


def canonical_json(value: object) -> str:
    """Serialize supported manifest values deterministically."""
    return json.dumps(_freeze(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_value(value: object) -> str:
    """Return a tagged SHA-256 digest of canonical JSON data."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fingerprint_files(paths: Iterable[Path], project_root: Path) -> list[dict[str, object]]:
    """Hash each unique file and return a stable, path-sorted description."""
    root = project_root.resolve()
    unique_paths = sorted({Path(path).resolve() for path in paths}, key=lambda path: _display_path(path, root))
    fingerprints: list[dict[str, object]] = []
    for path in unique_paths:
        if not path.is_file():
            raise ManifestError(f"required manifest input file does not exist: {path}")
        fingerprints.append(
            {
                "path": _display_path(path, root),
                "size_bytes": path.stat().st_size,
                "sha256": f"sha256:{_sha256_file(path)}",
            }
        )
    return fingerprints


def fingerprint_dataframe(frame: pd.DataFrame, name: str) -> dict[str, object]:
    """Create a deterministic content fingerprint for an in-memory market-data snapshot."""
    metadata: dict[str, object] = {
        "name": name,
        "row_count": len(frame),
        "columns": [str(column) for column in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
    }
    if "time" in frame.columns and not frame.empty:
        metadata["first_timestamp"] = _freeze(frame["time"].iloc[0])
        metadata["last_timestamp"] = _freeze(frame["time"].iloc[-1])
    digest = hashlib.sha256(canonical_json(metadata).encode("utf-8"))
    try:
        row_hashes = pd.util.hash_pandas_object(frame, index=True, categorize=True).to_numpy(dtype="<u8")
    except (TypeError, ValueError) as error:
        raise ManifestError(f"could not hash in-memory dataset {name!r}: {error}") from error
    digest.update(row_hashes.tobytes())
    return {**metadata, "sha256": f"sha256:{digest.hexdigest()}"}


def local_archive_dataset(
    *,
    archive_root: Path,
    archive: object,
    symbol: str,
    periods: Sequence[tuple[datetime, datetime]],
    project_root: Path = Path("."),
) -> dict[str, object]:
    """Describe and hash every annual archive file touched by exact periods."""
    provider_paths: dict[str, set[Path]] = {}
    source_directories = {"histdata": "histdata", "dukascopy": "dukascopy_annual"}
    source_for_range = getattr(archive, "source_for_range", None)
    if not callable(source_for_range):
        raise ManifestError("archive must provide source_for_range(start, end)")
    for start, end in periods:
        source = source_for_range(start, end)
        if source not in source_directories:
            raise ManifestError(f"unsupported local archive provider: {source!r}")
        last_year = (end - pd.Timedelta(1, unit="us")).year
        provider_paths.setdefault(source, set()).update(
            archive_root / source_directories[source] / f"{symbol.upper()}_m1_{year}.csv.gz"
            for year in range(start.year, last_year + 1)
        )
    segments = [
        {"provider": provider, "files": fingerprint_files(paths, project_root)}
        for provider, paths in sorted(provider_paths.items())
    ]
    description = {
        "kind": "local_annual_m1_ohlcv_archive",
        "archive_root": _display_path(archive_root.resolve(), project_root.resolve()),
        "provider_segments": segments,
    }
    return {**description, "identifier": sha256_value(description)}

def strategy_descriptor(name: str, strategy_type: type[object], project_root: Path) -> dict[str, object]:
    """Describe a fixed-rule strategy without capturing mutable runtime state."""
    source_paths: set[Path] = set()
    for implementation_type in strategy_type.__mro__:
        if implementation_type is object:
            continue
        source_file = inspect.getsourcefile(implementation_type)
        if source_file is not None:
            source_paths.add(Path(source_file))
    if not source_paths:
        raise ManifestError(f"could not locate source for strategy {name!r}")
    implementation_files = fingerprint_files(source_paths, project_root)
    parameters = _constructor_defaults(strategy_type)
    implementation = {
        "module": strategy_type.__module__,
        "qualified_name": strategy_type.__qualname__,
        "source_files": implementation_files,
    }
    implementation["identifier"] = sha256_value(implementation)
    return {
        "strategy_name": name,
        "implementation": implementation,
        "parameters": parameters,
    }


def build_run_manifest(
    *,
    run_kind: str,
    execution_timestamp: datetime,
    strategies: Mapping[str, type[object]],
    symbol: str,
    timeframe: str,
    periods: Mapping[str, object],
    dataset: Mapping[str, object],
    transaction_costs: Mapping[str, object],
    starting_equity: float,
    risk_settings: Mapping[str, object],
    symbol_settings: Mapping[str, object],
    runner_settings: Mapping[str, object],
    strategy_parameters: Mapping[str, Mapping[str, object]] | None = None,
    relevant_code_objects: Sequence[object] = (),
    relevant_code_paths: Sequence[Path] = (),
    random_seed: int | None = None,
    project_root: Path = Path("."),
) -> dict[str, object]:
    """Build a canonical manifest whose compatibility hash excludes wall-clock metadata."""
    if execution_timestamp.tzinfo is None:
        raise ManifestError("execution_timestamp must be timezone-aware")
    if not strategies:
        raise ManifestError("at least one strategy is required")

    unknown_parameters = set(strategy_parameters or ()) - set(strategies)
    if unknown_parameters:
        raise ManifestError(f"strategy parameters supplied for unknown strategies: {sorted(unknown_parameters)}")
    strategy_descriptors = []
    for name, strategy_type in sorted(strategies.items()):
        descriptor = strategy_descriptor(name, strategy_type, project_root)
        if strategy_parameters is not None and name in strategy_parameters:
            descriptor["parameters"] = _freeze(strategy_parameters[name])
        strategy_descriptors.append(descriptor)
    code_paths = {Path(path) for path in relevant_code_paths}
    code_paths.add(Path(__file__))
    for code_object in relevant_code_objects:
        source_file = inspect.getsourcefile(code_object)
        if source_file is None:
            raise ManifestError(f"could not locate relevant source for {code_object!r}")
        code_paths.add(Path(source_file))
    for descriptor in strategy_descriptors:
        for source in descriptor["implementation"]["source_files"]:  # type: ignore[index]
            source_path = project_root / str(source["path"])
            if source_path.is_file():
                code_paths.add(source_path)
    code_files = fingerprint_files(code_paths, project_root)
    code = {"algorithm": "sha256", "files": code_files}
    code["identifier"] = sha256_value(code_files)

    frozen = {
        "run_kind": run_kind,
        "strategies": strategy_descriptors,
        "symbol": symbol,
        "timeframe": timeframe,
        "periods": periods,
        "dataset": dataset,
        "transaction_costs": transaction_costs,
        "starting_equity": starting_equity,
        "risk_settings": risk_settings,
        "symbol_settings": symbol_settings,
        "runner_settings": runner_settings,
        "random_seed": random_seed,
        "code": code,
    }
    frozen = _freeze(frozen)
    compatibility_hash = sha256_value(frozen)
    suffix = compatibility_hash.removeprefix("sha256:")[:16]
    experiments = [
        {
            "experiment_id": f"{descriptor['strategy_name']}:{suffix}",
            "strategy_name": descriptor["strategy_name"],
        }
        for descriptor in strategy_descriptors
    ]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": f"{run_kind}:{suffix}",
        "execution_timestamp": execution_timestamp.isoformat(),
        "compatibility_hash": compatibility_hash,
        "experiments": experiments,
        "frozen": frozen,
    }


def validate_manifest_compatibility(saved: Mapping[str, object], expected: Mapping[str, object]) -> None:
    """Reject any resume whose frozen research inputs differ."""
    _validate_manifest_integrity(saved, "checkpoint")
    _validate_manifest_integrity(expected, "requested run")
    if saved["compatibility_hash"] == expected["compatibility_hash"]:
        return
    differences = _different_paths(saved["frozen"], expected["frozen"])
    detail = ", ".join(differences[:12]) or "compatibility_hash"
    if len(differences) > 12:
        detail += f", and {len(differences) - 12} more"
    raise CheckpointCompatibilityError(
        "checkpoint manifest is incompatible with the requested run; differing frozen fields: "
        f"{detail}. Use a new report path or pass --restart to explicitly start over."
    )


def load_compatible_checkpoint(path: Path, expected_manifest: Mapping[str, object]) -> dict[str, object] | None:
    """Load a checkpoint only after validating its embedded manifest."""
    if not path.exists():
        return None
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckpointCompatibilityError(f"could not read checkpoint {path}: {error}") from error
    if not isinstance(checkpoint, dict):
        raise CheckpointCompatibilityError("checkpoint root must be a JSON object")
    if checkpoint.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointCompatibilityError(
            "legacy or unsupported checkpoint has no compatible manifest; "
            "use a new report path or pass --restart to explicitly start over"
        )
    saved_manifest = checkpoint.get("manifest")
    if not isinstance(saved_manifest, dict):
        raise CheckpointCompatibilityError(
            "checkpoint does not contain a run manifest; use a new report path or pass --restart"
        )
    validate_manifest_compatibility(saved_manifest, expected_manifest)
    if not isinstance(checkpoint.get("results"), list) or not isinstance(checkpoint.get("skipped_windows"), list):
        raise CheckpointCompatibilityError("checkpoint results and skipped_windows must be JSON arrays")
    return checkpoint


def checkpoint_document(
    manifest: Mapping[str, object], results: Sequence[Mapping[str, object]], skipped_windows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Build the complete checkpoint payload written after each unit of work."""
    return {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "manifest": dict(manifest),
        "results": list(results),
        "skipped_windows": list(skipped_windows),
    }


def write_json_atomic(path: Path, value: object) -> None:
    """Write JSON via an adjacent temporary file so interruptions do not corrupt state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise ManifestError(f"could not write JSON file {path}: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _constructor_defaults(strategy_type: type[object]) -> dict[str, object]:
    try:
        signature = inspect.signature(strategy_type)
    except (TypeError, ValueError) as error:
        raise ManifestError(f"could not inspect strategy constructor {strategy_type!r}") from error
    parameters: dict[str, object] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if parameter.default is inspect.Parameter.empty:
            raise ManifestError(
                f"strategy {strategy_type.__qualname__} has required constructor parameter {name!r}; "
                "the runner must provide its frozen value explicitly"
            )
        parameters[name] = _freeze(parameter.default)
    return parameters


def _validate_manifest_integrity(manifest: Mapping[str, object], label: str) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise CheckpointCompatibilityError(f"{label} uses an unsupported manifest schema")
    frozen = manifest.get("frozen")
    compatibility_hash = manifest.get("compatibility_hash")
    if not isinstance(frozen, dict) or not isinstance(compatibility_hash, str):
        raise CheckpointCompatibilityError(f"{label} manifest is missing frozen inputs or compatibility hash")
    if sha256_value(frozen) != compatibility_hash:
        raise CheckpointCompatibilityError(f"{label} manifest compatibility hash does not match its frozen inputs")


def _freeze(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ManifestError("manifest values must not contain NaN or infinity")
        return value
    if isinstance(value, BaseModel):
        return _freeze(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _freeze(asdict(value))
    if isinstance(value, Enum):
        return _freeze(value.value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_freeze(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_freeze(item) for item in value), key=canonical_json)
    raise ManifestError(f"unsupported manifest value type: {type(value).__qualname__}")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ManifestError(f"could not hash manifest input file {path}: {error}") from error
    return digest.hexdigest()


def _different_paths(saved: object, expected: object, prefix: str = "frozen") -> list[str]:
    if isinstance(saved, dict) and isinstance(expected, dict):
        differences: list[str] = []
        for key in sorted(set(saved) | set(expected)):
            path = f"{prefix}.{key}"
            if key not in saved or key not in expected:
                differences.append(path)
            else:
                differences.extend(_different_paths(saved[key], expected[key], path))
        return differences
    if isinstance(saved, list) and isinstance(expected, list):
        differences = []
        for index in range(max(len(saved), len(expected))):
            path = f"{prefix}[{index}]"
            if index >= len(saved) or index >= len(expected):
                differences.append(path)
            else:
                differences.extend(_different_paths(saved[index], expected[index], path))
        return differences
    return [] if saved == expected else [prefix]
