from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

import pandas as pd
import pytest

from mt5_scalping_agent.research.manifest import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointCompatibilityError,
    build_run_manifest,
    checkpoint_document,
    fingerprint_files,
    load_compatible_checkpoint,
    validate_manifest_compatibility,
    write_json_atomic,
)


@dataclass(frozen=True)
class _StrategyConfig:
    threshold: float = 2.0
    session_start: time = time(12)


class _FixedStrategy:
    def __init__(self, config: _StrategyConfig = _StrategyConfig()) -> None:
        self._config = config


@dataclass(frozen=True)
class _ChangedStrategyConfig:
    threshold: float = 3.0
    session_start: time = time(12)


class _ChangedStrategy:
    def __init__(self, config: _ChangedStrategyConfig = _ChangedStrategyConfig()) -> None:
        self._config = config


def _manifest(
    tmp_path: Path,
    *,
    timestamp: datetime = datetime(2026, 8, 24, 12, tzinfo=UTC),
    spread: float = 1.0,
    risk_percent: float = 0.5,
    strategy_type: type[object] = _FixedStrategy,
    data_contents: str = "one",
    code_contents: str = "version-one",
    strategy_parameters: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    data_path = tmp_path / "EURUSD_m1_2023.csv.gz"
    code_path = tmp_path / "runner_source.py"
    data_path.write_text(data_contents, encoding="utf-8")
    code_path.write_text(code_contents, encoding="utf-8")
    data_files = fingerprint_files([data_path], tmp_path)
    return build_run_manifest(
        run_kind="test_validation",
        execution_timestamp=timestamp,
        strategies={"fixed": strategy_type},
        strategy_parameters=strategy_parameters,
        symbol="EURUSD",
        timeframe="M1",
        periods={"development": {"start": "2023-01-01", "end": "2024-01-01"}},
        dataset={"source": "test", "files": data_files},
        transaction_costs={
            "spread_points": spread,
            "slippage_points": 0.5,
            "commission_model": {"kind": "fixed_per_lot_per_side", "amount": 2.0},
        },
        starting_equity=10_000.0,
        risk_settings={"risk_percent_per_trade": risk_percent},
        symbol_settings={"point": 0.00001},
        runner_settings={"window_days": 28},
        relevant_code_paths=[code_path],
        random_seed=None,
        project_root=tmp_path,
    )


def test_manifest_records_frozen_strategy_inputs_and_file_hashes(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    frozen = manifest["frozen"]
    strategy = frozen["strategies"][0]
    assert manifest["run_id"].startswith("test_validation:")
    assert manifest["experiments"][0]["strategy_name"] == "fixed"
    assert strategy["implementation"]["identifier"].startswith("sha256:")
    assert strategy["parameters"] == {
        "config": {"session_start": "12:00:00", "threshold": 2.0}
    }
    assert frozen["dataset"]["files"][0]["sha256"].startswith("sha256:")
    assert frozen["code"]["identifier"].startswith("sha256:")
    assert frozen["random_seed"] is None


def test_timestamp_does_not_change_compatibility_or_experiment_id(tmp_path: Path) -> None:
    saved = _manifest(tmp_path)
    expected = _manifest(tmp_path, timestamp=datetime(2026, 8, 24, 13, tzinfo=UTC))

    validate_manifest_compatibility(saved, expected)

    assert saved["compatibility_hash"] == expected["compatibility_hash"]
    assert saved["experiments"] == expected["experiments"]
    assert saved["execution_timestamp"] != expected["execution_timestamp"]


@pytest.mark.parametrize(
    ("change", "expected_path"),
    [
        ({"spread": 2.0}, "transaction_costs.spread_points"),
        ({"risk_percent": 1.0}, "risk_settings.risk_percent_per_trade"),
        ({"strategy_type": _ChangedStrategy}, "strategies[0]"),
        ({"data_contents": "two"}, "dataset.files[0].sha256"),
        ({"code_contents": "version-two"}, "code.files"),
    ],
)
def test_changed_frozen_inputs_reject_checkpoint_resume(
    tmp_path: Path, change: dict[str, object], expected_path: str
) -> None:
    saved = _manifest(tmp_path)
    expected = _manifest(tmp_path, **change)

    with pytest.raises(CheckpointCompatibilityError, match=expected_path.replace("[", r"\[").replace("]", r"\]")):
        validate_manifest_compatibility(saved, expected)


def test_compatible_checkpoint_loads_and_preserves_original_manifest(tmp_path: Path) -> None:
    path = tmp_path / "run.checkpoint.json"
    saved = _manifest(tmp_path)
    expected = _manifest(tmp_path, timestamp=datetime(2026, 8, 25, 12, tzinfo=UTC))
    write_json_atomic(path, checkpoint_document(saved, [{"strategy": "fixed"}], []))

    loaded = load_compatible_checkpoint(path, expected)

    assert loaded is not None
    assert loaded["checkpoint_schema_version"] == CHECKPOINT_SCHEMA_VERSION
    assert loaded["manifest"]["execution_timestamp"] == saved["execution_timestamp"]
    assert loaded["results"] == [{"strategy": "fixed"}]


def test_legacy_checkpoint_is_never_silently_resumed(tmp_path: Path) -> None:
    path = tmp_path / "legacy.checkpoint.json"
    write_json_atomic(path, {"results": [], "skipped_windows": []})

    with pytest.raises(CheckpointCompatibilityError, match="legacy or unsupported checkpoint"):
        load_compatible_checkpoint(path, _manifest(tmp_path))


def test_manifest_tampering_is_detected_even_if_stored_hash_is_unchanged(tmp_path: Path) -> None:
    saved = _manifest(tmp_path)
    expected = _manifest(tmp_path)
    saved["frozen"]["starting_equity"] = 50_000.0

    with pytest.raises(CheckpointCompatibilityError, match="does not match its frozen inputs"):
        validate_manifest_compatibility(saved, expected)

def test_dataframe_fingerprint_is_stable_and_content_sensitive() -> None:
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "close": [1.1, 1.2],
        }
    )

    from mt5_scalping_agent.research import fingerprint_dataframe

    first = fingerprint_dataframe(frame, "M1")
    second = fingerprint_dataframe(frame.copy(), "M1")
    changed = frame.copy()
    changed.loc[1, "close"] = 1.3

    assert first == second
    assert fingerprint_dataframe(changed, "M1")["sha256"] != first["sha256"]


def test_explicit_frozen_strategy_parameters_override_constructor_defaults(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        strategy_parameters={"fixed": {"threshold": 9.0, "mode": "frozen"}},
    )

    assert manifest["frozen"]["strategies"][0]["parameters"] == {
        "mode": "frozen",
        "threshold": 9.0,
    }