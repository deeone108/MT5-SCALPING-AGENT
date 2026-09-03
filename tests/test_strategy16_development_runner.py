from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import PositionSizingMode
from mt5_scalping_agent.research.continuous_evaluation import SplitIsolationError
from scripts.run_strategy16_development import (
    BASE_COST_MODEL_ID,
    BLOCK_BOOTSTRAP_SAMPLES,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_IMPLEMENTATION,
    EXPECTED_PREREGISTRATION_FINGERPRINT,
    FIXED_VOLUME_LOTS,
    SCENARIOS,
    STRESS_COST_MODEL_ID,
    _backtest_config,
    _development_dataset,
    _isolated_periods,
    _load_development_candles,
    _load_frozen_governance,
    _new_strategy,
    _validate_exact_development_scope,
    parse_arguments,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_cannot_change_dates_costs_volume_or_strategy() -> None:
    args = parse_arguments([])

    assert not hasattr(args, "start")
    assert not hasattr(args, "end")
    assert not hasattr(args, "spread_points")
    assert not hasattr(args, "slippage_points")
    assert not hasattr(args, "commission_per_lot")
    assert not hasattr(args, "fixed_volume_lots")
    assert not hasattr(args, "strategies")
    assert BLOCK_BOOTSTRAP_SAMPLES == 10_000
    assert FIXED_VOLUME_LOTS == 1.0


def test_period_is_exact_and_post_selection_is_frozen_out() -> None:
    start, end = _validate_exact_development_scope(
        DEVELOPMENT_START, DEVELOPMENT_END
    )
    periods = _isolated_periods(start, end)

    assert periods["development"] == {
        "start": "2019-01-01T00:00:00+00:00",
        "end": "2024-01-01T00:00:00+00:00",
        "end_exclusive": True,
    }
    assert periods["post_selection_robustness"]["permitted_for_this_run"] is False

    with pytest.raises(SplitIsolationError, match="exactly"):
        _validate_exact_development_scope(
            DEVELOPMENT_START,
            datetime(2024, 1, 2, tzinfo=UTC),
        )
    with pytest.raises(SplitIsolationError, match="timezone-aware"):
        _validate_exact_development_scope(
            datetime(2019, 1, 1), DEVELOPMENT_END
        )


def test_invalid_scope_fails_before_archive_construction_or_access(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class FakeArchive:
        def __init__(self, root: Path) -> None:
            calls.append(f"construct:{root}")

        def source_for_range(self, start: datetime, end: datetime) -> str:
            calls.append("source")
            return "dukascopy"

        def load_m1(
            self, symbol: str, start: datetime, end: datetime
        ) -> pd.DataFrame:
            calls.append("load")
            raise AssertionError("invalid scope must not load")

    with pytest.raises(SplitIsolationError, match="2024-2026 is forbidden"):
        _load_development_candles(
            tmp_path,
            DEVELOPMENT_START,
            datetime(2024, 1, 2, tzinfo=UTC),
            archive_factory=FakeArchive,
        )

    assert calls == []


def test_non_dukascopy_provider_is_rejected_before_loading(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeArchive:
        def __init__(self, root: Path) -> None:
            calls.append("construct")

        def source_for_range(self, start: datetime, end: datetime) -> str:
            calls.append("source")
            return "histdata"

        def load_m1(
            self, symbol: str, start: datetime, end: datetime
        ) -> pd.DataFrame:
            calls.append("load")
            raise AssertionError("wrong provider must not load")

    with pytest.raises(SplitIsolationError, match="only the Dukascopy"):
        _load_development_candles(
            tmp_path,
            DEVELOPMENT_START,
            DEVELOPMENT_END,
            archive_factory=FakeArchive,
        )

    assert calls == ["construct", "source"]


def test_dataset_fingerprint_uses_only_accepted_2019_2023_files(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "data"
    annual = archive_root / "dukascopy_annual"
    annual.mkdir(parents=True)
    for year in range(2019, 2024):
        (annual / f"EURUSD_m1_{year}.csv.gz").write_bytes(str(year).encode())
    (annual / "EURUSD_m1_2024.csv.gz").write_bytes(b"forbidden")

    dataset = _development_dataset(archive_root, "EURUSD", tmp_path)
    segment = dataset["provider_segments"][0]

    assert segment["provider"] == "dukascopy"
    assert [Path(row["path"]).name for row in segment["files"]] == [
        f"EURUSD_m1_{year}.csv.gz" for year in range(2019, 2024)
    ]


def test_cost_scenarios_and_fixed_lot_configs_are_not_adjustable() -> None:
    base, stress = SCENARIOS

    assert (base.cost_model_id, base.spread_points, base.slippage_points) == (
        BASE_COST_MODEL_ID,
        4.0,
        2.0,
    )
    assert (stress.cost_model_id, stress.spread_points, stress.slippage_points) == (
        STRESS_COST_MODEL_ID,
        10.0,
        5.0,
    )
    assert base.commission_per_lot_per_side == 2.0
    assert stress.commission_per_lot_per_side == 2.0
    assert (base.all_in_cost_pips, stress.all_in_cost_pips) == (1.0, 1.9)
    for scenario in SCENARIOS:
        config = _backtest_config(scenario)
        assert config.position_sizing_mode is PositionSizingMode.RESEARCH_FIXED_LOT
        assert config.fixed_volume_lots == 1.0


def test_each_cost_scenario_gets_a_fresh_strategy_instance() -> None:
    constructed: list[tuple[float, float]] = []

    class FakeStrategy:
        def __init__(
            self,
            *,
            spread_points: float,
            all_in_cost_pips: float,
        ) -> None:
            constructed.append((spread_points, all_in_cost_pips))

    candles = pd.DataFrame()
    first = _new_strategy(candles, SCENARIOS[0], strategy_type=FakeStrategy)  # type: ignore[arg-type]
    second = _new_strategy(candles, SCENARIOS[1], strategy_type=FakeStrategy)  # type: ignore[arg-type]

    assert first is not second
    assert constructed == [(4.0, 1.0), (10.0, 1.9)]


def test_runner_refuses_rejected_registry_before_archive_access() -> None:
    with pytest.raises(ValueError, match="must be in DEVELOPMENT"):
        _load_frozen_governance(
            PROJECT_ROOT / "config/research_registry.json", PROJECT_ROOT
        )

