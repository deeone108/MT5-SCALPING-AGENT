"""Evaluate frozen Strategy 17 on the isolated 2019-2023 development split.

This module is research-only. It has no broker connection or order-submission
path, and its dates and transaction-cost scenarios are intentionally not CLI
options.
"""

from __future__ import annotations

import argparse
import gc
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import ceil, isfinite
from pathlib import Path
from sys import float_info
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd

from mt5_scalping_agent.backtesting import (
    BacktestConfig,
    BacktestResult,
    CandleBacktester,
    PositionSizingMode,
)
from mt5_scalping_agent.backtesting.london_new_york_intraday import (
    LondonNewYorkIntradayConfig,
    LondonNewYorkIntradayContinuationStrategy,
)
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research import (
    build_run_manifest,
    checkpoint_document,
    fingerprint_files,
    load_compatible_checkpoint,
    sha256_value,
    write_json_atomic,
)
from mt5_scalping_agent.research.continuous_evaluation import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    POST_SELECTION_START,
    SplitIsolationError,
    VolatilityRegimeSettings,
    causal_volatility_regimes,
)
from mt5_scalping_agent.research.registry import (
    DEFAULT_REGISTRY_PATH,
    EconomicPromotionGate,
    ResearchDecision,
    ResearchStatus,
    load_research_registry,
    preregistration_fingerprint,
)
from mt5_scalping_agent.research.signal_economics import signal_economics_report
from mt5_scalping_agent.research.statistical_robustness import (
    StatisticalRobustnessSettings,
)
from mt5_scalping_agent.research.strategy17_evaluation import (
    BlockBootstrapSettings,
    Strategy16GateMetrics,
    block_bootstrap_report,
    strategy17_gate_report,
)
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


STRATEGY_NAME = "london_new_york_intraday_continuation"
RESEARCH_ID = "strategy_16_london_new_york_intraday_continuation_v1"
EXPECTED_IMPLEMENTATION = (
    "mt5_scalping_agent.backtesting.london_new_york_intraday."
    "LondonNewYorkIntradayContinuationStrategy"
)
EXPECTED_PREREGISTRATION_FINGERPRINT = (
    "sha256:41850803b46be1f9eec948ee2a1184f346933b1570db244f77863f65e90e522e"
)
DEVELOPMENT_DATASET_ID = "dukascopy_eurusd_m1_development_2019_2023"
BASE_COST_MODEL_ID = "roboforex_ecn_eurusd_intraday_base_v1"
STRESS_COST_MODEL_ID = "roboforex_ecn_eurusd_intraday_stress_v1"
PROMOTION_GATE_ID = "strategy_17_intraday_economic_gate_v1"
FIXED_VOLUME_LOTS = 1.0
INITIAL_BALANCE = 10_000.0
BLOCK_BOOTSTRAP_SEED = 20_260_831
BLOCK_BOOTSTRAP_SAMPLES = 10_000
DEFAULT_REPORT_PATH = Path(
    "reports/strategy17/eurusd_2019_2023_strategy17_development.json"
)


@dataclass(frozen=True)
class CostScenario:
    name: str
    cost_model_id: str
    spread_points: float
    slippage_points: float
    commission_per_lot_per_side: float
    all_in_cost_pips: float


SCENARIOS = (
    CostScenario("base", BASE_COST_MODEL_ID, 1.0, 1.0, 2.0, 0.6),
    CostScenario("stress", STRESS_COST_MODEL_ID, 3.0, 2.0, 2.0, 0.9),
)


@dataclass(frozen=True)
class FrozenGovernance:
    strategy_parameters: Mapping[str, object]
    gate: EconomicPromotionGate
    preregistration_fingerprint: str


class _Strategy16ManifestBinding:
    """Zero-argument manifest binding for a data-injected strategy class."""


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen Strategy 17 at unit exposure under its base and stress "
            "costs on exactly [2019-01-01, 2024-01-01). No 2024+ data can be loaded."
        )
    )
    parser.add_argument("--archive-root", type=Path, default=Path("data"))
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--restart",
        action="store_true",
        help="explicitly replace a checkpoint instead of resuming a compatible run",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    return _run_development(parse_arguments(arguments))


def _run_development(
    args: argparse.Namespace,
    *,
    development_start: datetime = DEVELOPMENT_START,
    development_end: datetime = DEVELOPMENT_END,
    archive_factory: Callable[[Path], object] | None = None,
) -> int:
    start, end = _validate_exact_development_scope(
        development_start, development_end
    )
    project_root = Path.cwd()

    # Governance is checked before archive fingerprints, construction, or loading.
    governance = _load_frozen_governance(args.registry_path, project_root)
    symbol = _symbol_spec()
    risk_limits = _unit_exposure_risk_limits()
    periods = _isolated_periods(start, end)
    dataset = _development_dataset(args.archive_root, symbol.symbol, project_root)
    volatility_settings = VolatilityRegimeSettings()
    iid_diagnostic_settings = StatisticalRobustnessSettings(
        random_seed=BLOCK_BOOTSTRAP_SEED,
        bootstrap_samples=1_000,
    )
    block_settings = BlockBootstrapSettings(
        random_seed=BLOCK_BOOTSTRAP_SEED,
        bootstrap_samples=BLOCK_BOOTSTRAP_SAMPLES,
        confidence_level=governance.gate.bootstrap_confidence_level,
        block_units=governance.gate.bootstrap_units,
        minimum_meaningful_stress_net_margin_pips=(
            governance.gate.minimum_stress_net_expectancy_pips
        ),
    )
    configs = {
        scenario.name: _backtest_config(scenario) for scenario in SCENARIOS
    }
    registry_fingerprint = fingerprint_files((args.registry_path,), project_root)[0]
    expected_manifest = build_run_manifest(
        run_kind="strategy17_development_unit_economics",
        execution_timestamp=datetime.now(UTC),
        strategies={STRATEGY_NAME: _Strategy16ManifestBinding},
        strategy_parameters={
            STRATEGY_NAME: dict(governance.strategy_parameters)
        },
        symbol=symbol.symbol,
        timeframe="M1 with strict causal M5/M15 aggregation",
        periods=periods,
        dataset=dataset,
        transaction_costs={
            "scenarios": [_scenario_document(item) for item in SCENARIOS],
            "cost_selection": "both frozen scenarios; no optimization",
        },
        starting_equity=INITIAL_BALANCE,
        risk_settings=risk_limits.model_dump(mode="json"),
        symbol_settings=symbol.model_dump(mode="json"),
        runner_settings={
            "strategy_research_id": RESEARCH_ID,
            "preregistration_fingerprint": governance.preregistration_fingerprint,
            "registry_file": registry_fingerprint,
            "position_sizing_mode": PositionSizingMode.RESEARCH_FIXED_LOT.value,
            "fixed_volume_lots": FIXED_VOLUME_LOTS,
            "same_candle_snapshot_for_cost_scenarios": True,
            "fresh_strategy_instance_per_scenario": True,
            "calendar_diagnostics": ["year", "quarter", "month"],
            "categorical_diagnostics": [
                "direction",
                "DST-aware session",
                "causal volatility regime",
            ],
            "iid_bootstrap_role": "diagnostic_only_not_a_promotion_gate",
            "block_bootstrap": block_settings.as_dict(),
            "block_bootstrap_execution": "only after all primary gates pass",
            "post_selection_data_access": "forbidden",
            "broker_execution": "absent",
        },
        relevant_code_objects=(
            BacktestConfig,
            CandleBacktester,
            LondonNewYorkIntradayConfig,
            LondonNewYorkIntradayContinuationStrategy,
            LocalResearchArchive,
            RiskEngine,
            RiskLimits,
            SymbolRiskSpec,
            block_bootstrap_report,
            causal_volatility_regimes,
            signal_economics_report,
            strategy17_gate_report,
        ),
        relevant_code_paths=(
            Path(__file__),
            args.registry_path,
            Path("docs/STRATEGY_17_RESEARCH_BRIEF.md"),
        ),
        random_seed=BLOCK_BOOTSTRAP_SEED,
        project_root=project_root,
    )

    checkpoint_path = args.report_path.with_suffix(".checkpoint.json")
    manifest_path = args.report_path.with_suffix(".manifest.json")
    checkpoint = (
        None
        if args.restart
        else load_compatible_checkpoint(checkpoint_path, expected_manifest)
    )
    if checkpoint is None:
        run_manifest = expected_manifest
        results: list[dict[str, object]] = []
        write_json_atomic(
            checkpoint_path, checkpoint_document(run_manifest, results, ())
        )
    else:
        run_manifest = cast(dict[str, object], checkpoint["manifest"])
        results = cast(list[dict[str, object]], checkpoint["results"])
        _validate_checkpoint_results(results, args.report_path, project_root)
    write_json_atomic(manifest_path, run_manifest)

    candles = _load_development_candles(
        args.archive_root,
        start,
        end,
        archive_factory=archive_factory,
    )
    volatility = causal_volatility_regimes(candles, volatility_settings)
    completed = {str(row["scenario"]) for row in results}
    runtime_results: dict[str, BacktestResult] = {}
    evaluations = _load_completed_evaluations(results, project_root)

    for scenario in SCENARIOS:
        if scenario.name in completed:
            print(f"Skipping completed Strategy 17 {scenario.name} scenario", flush=True)
            continue
        print(
            f"Starting Strategy 17 {scenario.name} scenario at fixed 1.0 lot; "
            "checkpoint follows completion",
            flush=True,
        )
        result, strategy = _simulate_scenario(
            candles,
            scenario,
            symbol=symbol,
            risk_limits=risk_limits,
            config=configs[scenario.name],
        )
        evaluation = signal_economics_report(
            result,
            candles,
            strategy_name=STRATEGY_NAME,
            fixed_volume_lots=FIXED_VOLUME_LOTS,
            initial_balance=INITIAL_BALANCE,
            symbol=symbol,
            period_start=start,
            period_end=end,
            volatility_settings=volatility_settings,
            statistical_settings=iid_diagnostic_settings,
            precomputed_volatility=volatility,
        )
        detail = {
            "run_id": run_manifest["run_id"],
            "scenario": _scenario_document(scenario),
            "backtest_assumptions": configs[scenario.name].model_dump(mode="json"),
            "strategy_diagnostics": _diagnostics_document(strategy.diagnostics),
            "block_bootstrap": None,
            **evaluation,
        }
        detail_path = _detail_path(args.report_path, scenario.name)
        write_json_atomic(detail_path, detail)
        row = _result_row(detail, detail_path, project_root)
        results.append(row)
        write_json_atomic(
            checkpoint_path, checkpoint_document(run_manifest, results, ())
        )
        runtime_results[scenario.name] = result
        evaluations[scenario.name] = detail
        complete = cast(dict[str, object], detail["signal_economics"])["complete"]
        print(
            f"Completed {scenario.name}: signals={complete['signal_count']}; "
            "checkpoint saved",
            flush=True,
        )
        del strategy, evaluation
        gc.collect()

    metrics = _gate_metrics(evaluations, governance.gate)
    gate_report = strategy17_gate_report(metrics, governance.gate)
    if bool(gate_report["primary_economic_gates_passed"]):
        for scenario in SCENARIOS:
            result = runtime_results.get(scenario.name)
            if result is None:
                result, _ = _simulate_scenario(
                    candles,
                    scenario,
                    symbol=symbol,
                    risk_limits=risk_limits,
                    config=configs[scenario.name],
                )
            bootstrap = block_bootstrap_report(
                result.trades,
                symbol=symbol,
                period_start=start,
                period_end=end,
                settings=block_settings,
            )
            detail = evaluations[scenario.name]
            detail["block_bootstrap"] = bootstrap
            detail_path = _detail_path(args.report_path, scenario.name)
            write_json_atomic(detail_path, detail)
            replacement = _result_row(detail, detail_path, project_root)
            results = [
                replacement if row["scenario"] == scenario.name else row
                for row in results
            ]
        write_json_atomic(
            checkpoint_path, checkpoint_document(run_manifest, results, ())
        )
        metrics = _gate_metrics(evaluations, governance.gate)
        gate_report = strategy17_gate_report(metrics, governance.gate)

    report = {
        "purpose": (
            "prospectively frozen Strategy 17 development evaluation at constant "
            "unit exposure under base and stress costs"
        ),
        "symbol": symbol.symbol,
        "periods": periods,
        "preregistration_fingerprint": governance.preregistration_fingerprint,
        "run_manifest": run_manifest,
        "manifest_path": manifest_path.as_posix(),
        "cost_scenarios": [_scenario_document(item) for item in SCENARIOS],
        "gate_report": gate_report,
        "results": results,
        "stop_rule": (
            "If any primary or eligible block-bootstrap gate fails, mark Strategy 17 "
            "REJECTED and do not run neighborhoods, risk sizing, or 2024+ data."
        ),
    }
    write_json_atomic(args.report_path, report)
    print(f"Report: {args.report_path}", flush=True)
    return 0


def _validate_exact_development_scope(
    start: datetime, end: datetime
) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise SplitIsolationError("Strategy 17 development boundaries must be timezone-aware")
    normalized = (start.astimezone(UTC), end.astimezone(UTC))
    if normalized != (DEVELOPMENT_START, DEVELOPMENT_END):
        raise SplitIsolationError(
            "Strategy 17 development requires exactly [2019-01-01, 2024-01-01); "
            "2024-2026 is forbidden before development promotion"
        )
    return normalized


def _load_frozen_governance(
    registry_path: Path, project_root: Path
) -> FrozenGovernance:
    registry = load_research_registry(
        registry_path, project_root=project_root, validate_evidence=False
    )
    record = registry.by_strategy_name().get(STRATEGY_NAME)
    if record is None or record.research_id != RESEARCH_ID:
        raise ValueError("the frozen Strategy 17 registry record is missing")
    fingerprint = preregistration_fingerprint(registry, STRATEGY_NAME)
    if fingerprint != EXPECTED_PREREGISTRATION_FINGERPRINT:
        raise ValueError("Strategy 17 preregistration fingerprint changed; refuse evaluation")
    if record.status is not ResearchStatus.DEVELOPMENT:
        raise ValueError("Strategy 17 must be in DEVELOPMENT before archive access")
    if record.decision is not ResearchDecision.UNDECIDED:
        raise ValueError("Strategy 17 development must have an UNDECIDED decision")
    if record.implementation != EXPECTED_IMPLEMENTATION:
        raise ValueError("Strategy 17 registry implementation does not match frozen code")
    if record.experiments_performed:
        raise ValueError("first Strategy 17 development run requires zero prior experiments")
    if record.permitted_development_dataset_id != DEVELOPMENT_DATASET_ID:
        raise ValueError("Strategy 17 development dataset identity changed")
    if record.required_broker_cost_model_id != BASE_COST_MODEL_ID:
        raise ValueError("Strategy 17 base cost-model identity changed")
    if record.promotion_gate_id != PROMOTION_GATE_ID:
        raise ValueError("Strategy 17 promotion gate identity changed")

    datasets = {item.dataset_id: item for item in registry.development_datasets}
    dataset = datasets[DEVELOPMENT_DATASET_ID]
    if (
        dataset.symbol != "EURUSD"
        or dataset.timeframe != "M1"
        or dataset.start.isoformat() != "2019-01-01"
        or dataset.end_exclusive.isoformat() != "2024-01-01"
        or "Dukascopy" not in dataset.provider
    ):
        raise ValueError("Strategy 17 dataset specification is not exact Dukascopy 2019-2023")
    gates = {item.gate_id: item for item in registry.promotion_gates}
    gate = gates.get(PROMOTION_GATE_ID)
    if not isinstance(gate, EconomicPromotionGate):
        raise ValueError("Strategy 17 requires its frozen economic promotion gate")
    costs = {item.cost_model_id: item for item in registry.broker_cost_models}
    for scenario in SCENARIOS:
        model = costs.get(scenario.cost_model_id)
        if model is None or (
            model.spread_points,
            model.slippage_points,
            model.commission_per_lot_per_side,
        ) != (
            scenario.spread_points,
            scenario.slippage_points,
            scenario.commission_per_lot_per_side,
        ):
            raise ValueError(f"frozen {scenario.name} transaction costs changed")
    _validate_strategy_defaults(record.frozen_parameters)
    return FrozenGovernance(record.frozen_parameters, gate, fingerprint)


def _validate_strategy_defaults(frozen: Mapping[str, object]) -> None:
    defaults = asdict(LondonNewYorkIntradayConfig())
    for key, value in defaults.items():
        expected = frozen.get(key)
        if isinstance(expected, str) and hasattr(value, "isoformat"):
            observed = value.isoformat(timespec="minutes")
        else:
            observed = value.isoformat() if hasattr(value, "isoformat") else value
        if expected != observed:
            raise ValueError(f"Strategy 17 code default drifted from frozen parameter {key}")


def _isolated_periods(start: datetime, end: datetime) -> dict[str, object]:
    _validate_exact_development_scope(start, end)
    return {
        "development": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "end_exclusive": True,
        },
        "post_selection_robustness": {
            "start": POST_SELECTION_START.isoformat(),
            "permitted_for_this_run": False,
            "purpose": "preserved post-selection evidence; never loaded by this runner",
        },
    }


def _development_dataset(
    archive_root: Path, symbol: str, project_root: Path
) -> dict[str, object]:
    paths = tuple(
        archive_root / "dukascopy_annual" / f"{symbol.upper()}_m1_{year}.csv.gz"
        for year in range(2019, 2024)
    )
    files = fingerprint_files(paths, project_root)
    description = {
        "kind": "local_annual_m1_ohlcv_archive",
        "dataset_id": DEVELOPMENT_DATASET_ID,
        "archive_root": archive_root.as_posix(),
        "provider_segments": [{"provider": "dukascopy", "files": files}],
    }
    return {**description, "identifier": sha256_value(description)}


def _load_development_candles(
    archive_root: Path,
    start: datetime,
    end: datetime,
    *,
    archive_factory: Callable[[Path], object] | None = None,
) -> pd.DataFrame:
    start, end = _validate_exact_development_scope(start, end)
    factory = archive_factory or LocalResearchArchive
    archive = factory(archive_root)
    source_for_range = getattr(archive, "source_for_range", None)
    load_m1 = getattr(archive, "load_m1", None)
    if not callable(source_for_range) or not callable(load_m1):
        raise TypeError("archive must provide source_for_range and load_m1")
    if source_for_range(start, end) != "dukascopy":
        raise SplitIsolationError("Strategy 17 accepts only the Dukascopy provider")
    candles = validate_ohlcv(load_m1("EURUSD", start, end)).reset_index(drop=True)
    if not candles.empty and (
        bool((candles["time"] < start).any())
        or bool((candles["time"] >= end).any())
    ):
        raise SplitIsolationError("archive returned candles outside Strategy 17 development")
    return candles


def _symbol_spec() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )


def _unit_exposure_risk_limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_percent=100.0,
        max_weekly_loss_percent=100.0,
        max_drawdown_percent=100.0,
        max_consecutive_losses=2_147_483_647,
        max_trades_per_hour=2_147_483_647,
        max_trades_per_day=2_147_483_647,
        max_open_positions=1,
        max_exposure_lots=FIXED_VOLUME_LOTS,
        max_symbol_exposure_lots=FIXED_VOLUME_LOTS,
        max_lot_size=FIXED_VOLUME_LOTS,
        min_reward_risk_ratio=1.25,
        max_spread_points=10.0,
    )


def _backtest_config(scenario: CostScenario) -> BacktestConfig:
    return BacktestConfig(
        initial_balance=INITIAL_BALANCE,
        spread_points=scenario.spread_points,
        slippage_points=scenario.slippage_points,
        commission_per_lot_per_side=scenario.commission_per_lot_per_side,
        position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
        fixed_volume_lots=FIXED_VOLUME_LOTS,
    )


def _new_strategy(
    candles: pd.DataFrame,
    scenario: CostScenario,
    *,
    strategy_type: type[LondonNewYorkIntradayContinuationStrategy] = (
        LondonNewYorkIntradayContinuationStrategy
    ),
) -> LondonNewYorkIntradayContinuationStrategy:
    return strategy_type(
        spread_points=scenario.spread_points,
        all_in_cost_pips=scenario.all_in_cost_pips,
    )


def _simulate_scenario(
    candles: pd.DataFrame,
    scenario: CostScenario,
    *,
    symbol: SymbolRiskSpec,
    risk_limits: RiskLimits,
    config: BacktestConfig,
) -> tuple[BacktestResult, LondonNewYorkIntradayContinuationStrategy]:
    strategy = _new_strategy(candles, scenario)
    result = CandleBacktester(config, RiskEngine(risk_limits), symbol).run(
        candles, strategy
    )
    return result, strategy


def _gate_metrics(
    evaluations: Mapping[str, Mapping[str, object]],
    gate: EconomicPromotionGate,
) -> Strategy16GateMetrics:
    base, stress = evaluations["base"], evaluations["stress"]
    base_complete = _economics_complete(base)
    stress_complete = _economics_complete(stress)
    base_trades = cast(list[dict[str, object]], base["trades"])
    stress_trades = cast(list[dict[str, object]], stress["trades"])
    base_diag = cast(Mapping[str, object], base["strategy_diagnostics"])
    stress_diag = cast(Mapping[str, object], stress["strategy_diagnostics"])
    base_accepted = int(base_complete["signal_count"])
    stress_accepted = int(stress_complete["signal_count"])
    base_rejected = _rejected_count(base)
    stress_rejected = _rejected_count(stress)
    mfe = [_trade_metric(row, "mfe_pips") for row in base_trades]
    mfe = [value for value in mfe if value is not None]
    positive_years, year_count, strongest = _year_evidence(stress)
    positive_months, active_months = _month_evidence(stress)
    return Strategy16GateMetrics(
        base_emitted=int(base_diag["emitted_signal_count"]),
        base_accepted=base_accepted,
        base_rejected=base_rejected,
        stress_emitted=int(stress_diag["emitted_signal_count"]),
        stress_accepted=stress_accepted,
        stress_rejected=stress_rejected,
        gross_expectancy_pips=_finite_or_failure(
            cast(Mapping[str, object], base_complete["gross"]).get(
                "expectancy_pips_per_signal"
            )
        ),
        base_net_expectancy_pips=_finite_or_failure(
            cast(Mapping[str, object], base_complete["net"]).get(
                "expectancy_pips_per_signal"
            )
        ),
        stress_net_expectancy_pips=_finite_or_failure(
            cast(Mapping[str, object], stress_complete["net"]).get(
                "expectancy_pips_per_signal"
            )
        ),
        base_profit_factor=_profit_factor(base),
        stress_profit_factor=_profit_factor(stress),
        median_mfe_pips=_nested_number(base_complete, "mfe", "distribution_pips", "median"),
        mfe_exceedance_ratio=(
            sum(value > gate.mfe_exceedance_threshold_pips for value in mfe) / len(mfe) if mfe else None
        ),
        median_adverse_mae_pips=_nested_number(
            base_complete,
            "mae",
            "adverse_magnitude_distribution_pips",
            "median",
        ),
        base_cost_pips=1.0,
        stress_cost_pips=1.9,
        base_annual_trades=_annual_counts(base),
        stress_annual_trades=_annual_counts(stress),
        base_max_entries_day=_maximum_entries_per_ny_day(base_trades),
        stress_max_entries_day=_maximum_entries_per_ny_day(stress_trades),
        median_holding_minutes=_nested_number(
            base_complete, "holding_duration_minutes", "median"
        ),
        maximum_holding_minutes=_nested_number(
            base_complete, "holding_duration_minutes", "maximum"
        ),
        overnight_trades=_overnight_count(stress_trades),
        minimum_stop_pips=_planned_minimum(base_trades, "planned_stop_distance_pips"),
        minimum_reward_pips=_planned_minimum(base_trades, "planned_target_distance_pips"),
        minimum_stress_cost_adjusted_rr=_planned_minimum(
            stress_trades, "cost_adjusted_planned_reward_risk_ratio"
        ),
        stress_positive_years=positive_years,
        stress_year_count=year_count,
        stress_positive_active_months=positive_months,
        stress_active_months=active_months,
        stress_strongest_year_contribution=strongest,
        stress_top_decile_contribution=_top_decile_contribution(stress_trades),
        base_block_bootstrap=cast(Mapping[str, object] | None, base.get("block_bootstrap")),
        stress_block_bootstrap=cast(Mapping[str, object] | None, stress.get("block_bootstrap")),
        downside_tail_reported=_downside_tail_present(base, stress),
    )


def _scenario_document(scenario: CostScenario) -> dict[str, object]:
    return asdict(scenario)


def _diagnostics_document(diagnostics: object) -> dict[str, object]:
    return {
        "evaluated_event_dates": int(getattr(diagnostics, "evaluated_event_dates")),
        "eligible_signal_count": int(getattr(diagnostics, "eligible_signal_count")),
        "emitted_signal_count": int(getattr(diagnostics, "emitted_signal_count")),
        "daily_limit_block_count": int(getattr(diagnostics, "daily_limit_block_count")),
        "rejected_setup_counts": dict(getattr(diagnostics, "rejected_setup_counts")),
    }


def _detail_path(report_path: Path, scenario: str) -> Path:
    return report_path.parent / f"{report_path.stem}_details" / f"{scenario}.json"


def _result_row(
    detail: Mapping[str, object], detail_path: Path, project_root: Path
) -> dict[str, object]:
    return {
        "scenario": detail["scenario"]["name"],  # type: ignore[index]
        "cost_model_id": detail["scenario"]["cost_model_id"],  # type: ignore[index]
        "period": detail["period"],
        "summaries": detail["summaries"],
        "signal_economics": detail["signal_economics"],
        "strategy_diagnostics": detail["strategy_diagnostics"],
        "block_bootstrap": detail.get("block_bootstrap"),
        "trade_ledger": fingerprint_files((detail_path,), project_root)[0],
    }


def _load_completed_evaluations(
    results: Sequence[Mapping[str, object]], project_root: Path
) -> dict[str, dict[str, object]]:
    loaded: dict[str, dict[str, object]] = {}
    for row in results:
        ledger = cast(Mapping[str, object], row["trade_ledger"])
        path = project_root / str(ledger["path"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Strategy 17 detail is not an object: {path}")
        loaded[str(row["scenario"])] = payload
    return loaded


def _validate_checkpoint_results(
    results: Sequence[Mapping[str, object]],
    report_path: Path,
    project_root: Path,
) -> None:
    expected = {item.name for item in SCENARIOS}
    seen: set[str] = set()
    for row in results:
        scenario = str(row.get("scenario", ""))
        if scenario not in expected or scenario in seen:
            raise ValueError(f"checkpoint contains invalid Strategy 17 scenario: {scenario!r}")
        seen.add(scenario)
        expected_path = _detail_path(report_path, scenario).resolve()
        ledger = row.get("trade_ledger")
        if not isinstance(ledger, Mapping):
            raise ValueError(f"checkpoint scenario {scenario} has no trade ledger")
        actual_path = (project_root / str(ledger.get("path", ""))).resolve()
        if actual_path != expected_path:
            raise ValueError(f"checkpoint scenario {scenario} points to an unexpected ledger")
        actual = fingerprint_files((actual_path,), project_root)[0]
        if actual["sha256"] != ledger.get("sha256"):
            raise ValueError(f"checkpoint trade ledger changed for {scenario}")


def _economics_complete(report: Mapping[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], cast(Mapping[str, object], report["signal_economics"])["complete"])


def _rejected_count(report: Mapping[str, object]) -> int:
    signal = cast(Mapping[str, object], report["signal_definition"])
    return int(signal["rejected_intent_count"])


def _profit_factor(report: Mapping[str, object]) -> float | None:
    complete = cast(Mapping[str, object], cast(Mapping[str, object], report["summaries"])["complete"])
    value = complete.get("profit_factor")
    if value == "infinity":
        return float_info.max
    return float(value) if isinstance(value, (int, float)) and isfinite(float(value)) else None


def _annual_counts(report: Mapping[str, object]) -> tuple[int, ...]:
    economics = cast(Mapping[str, object], report["signal_economics"])
    return tuple(int(row["signal_count"]) for row in cast(Sequence[Mapping[str, object]], economics["by_year"]))


def _year_evidence(report: Mapping[str, object]) -> tuple[int, int, float | None]:
    economics = cast(Mapping[str, object], report["signal_economics"])
    rows = cast(Sequence[Mapping[str, object]], economics["by_year"])
    nets = [float(cast(Mapping[str, object], row["net"])["total_pips"]) for row in rows]
    positive = [value for value in nets if value > 0]
    contribution = max(positive) / sum(positive) if positive else None
    return len(positive), len(rows), contribution


def _month_evidence(report: Mapping[str, object]) -> tuple[int, int]:
    economics = cast(Mapping[str, object], report["signal_economics"])
    rows = cast(Sequence[Mapping[str, object]], economics["by_month"])
    active = [row for row in rows if int(row["signal_count"]) > 0]
    positive = [row for row in active if float(cast(Mapping[str, object], row["net"])["total_pips"]) > 0]
    return len(positive), len(active)


def _trade_metric(row: Mapping[str, object], name: str) -> float | None:
    economics = cast(Mapping[str, object], row["signal_economics"])
    value = economics.get(name)
    return float(value) if isinstance(value, (int, float)) and isfinite(float(value)) else None


def _planned_minimum(rows: Sequence[Mapping[str, object]], name: str) -> float | None:
    values = [_trade_metric(row, name) for row in rows]
    finite = [value for value in values if value is not None]
    return min(finite) if finite else None


def _maximum_entries_per_ny_day(rows: Sequence[Mapping[str, object]]) -> int:
    zone = ZoneInfo("America/New_York")
    counts = Counter(
        datetime.fromisoformat(str(row["entry_time"])).astimezone(zone).date()
        for row in rows
    )
    return max(counts.values(), default=0)


def _overnight_count(rows: Sequence[Mapping[str, object]]) -> int:
    zone = ZoneInfo("America/New_York")
    return sum(
        datetime.fromisoformat(str(row["entry_time"])).astimezone(zone).date()
        != datetime.fromisoformat(str(row["exit_time"])).astimezone(zone).date()
        for row in rows
    )


def _top_decile_contribution(rows: Sequence[Mapping[str, object]]) -> float | None:
    profits = [_trade_metric(row, "net_pips") for row in rows]
    positive = sorted((value for value in profits if value is not None and value > 0), reverse=True)
    if not positive:
        return None
    count = max(1, ceil(0.10 * len(rows)))
    return sum(positive[:count]) / sum(positive)


def _nested_number(value: Mapping[str, object], *path: str) -> float | None:
    current: object = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return float(current) if isinstance(current, (int, float)) and isfinite(float(current)) else None


def _finite_or_failure(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and isfinite(float(value)) else -float_info.max


def _downside_tail_present(base: Mapping[str, object], stress: Mapping[str, object]) -> bool:
    for report in (base, stress):
        bootstrap = report.get("block_bootstrap")
        units = bootstrap.get("by_block_unit") if isinstance(bootstrap, Mapping) else None
        if not isinstance(units, Mapping) or set(units) != {"day", "week"}:
            return False
        if any(
            not isinstance(row, Mapping) or "maximum_drawdown_pips" not in row
            for row in units.values()
        ):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
