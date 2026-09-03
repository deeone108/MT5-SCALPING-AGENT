"""Typed, evidence-checked registry for strategy research decisions."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


REGISTRY_SCHEMA_VERSION = 2
DEFAULT_REGISTRY_PATH = Path("config/research_registry.json")


class RegistryError(RuntimeError):
    """Raised when the research registry is unreadable or internally inconsistent."""


class ResearchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    DEVELOPMENT = "DEVELOPMENT"
    REJECTED = "REJECTED"
    ROBUSTNESS = "ROBUSTNESS"
    TICK_VALIDATION = "TICK_VALIDATION"
    DEMO_ELIGIBLE = "DEMO_ELIGIBLE"
    DEMO = "DEMO"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


class ResearchDecision(str, Enum):
    UNDECIDED = "UNDECIDED"
    REJECTED = "REJECTED"
    ADVANCE = "ADVANCE"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DevelopmentDataset(StrictModel):
    dataset_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    start: date
    end_exclusive: date
    path_pattern: str = Field(min_length=1)
    permitted_use: str = Field(min_length=1)
    excluded_from_tuning: tuple[str, ...]

    @model_validator(mode="after")
    def validate_period(self) -> DevelopmentDataset:
        if self.start >= self.end_exclusive:
            raise ValueError("development dataset start must precede end_exclusive")
        return self


class BrokerCostModel(StrictModel):
    cost_model_id: str = Field(min_length=1)
    broker: str = Field(min_length=1)
    account_type: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    point_size: float = Field(gt=0)
    spread_points: float = Field(ge=0)
    slippage_points: float = Field(ge=0)
    commission_per_lot_per_side: float = Field(ge=0)
    currency: str = Field(min_length=1)
    calibration_evidence: str = Field(min_length=1)

    @field_validator("point_size", "spread_points", "slippage_points", "commission_per_lot_per_side")
    @classmethod
    def finite_costs(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("cost values must be finite")
        return value


class PromotionGate(StrictModel):
    gate_schema_version: Literal[1] = 1
    gate_id: str = Field(min_length=1)
    declared_on: date
    provenance_note: str = Field(min_length=1)
    minimum_development_trades: int = Field(gt=0)
    require_positive_after_cost_expectancy: bool
    minimum_profit_factor: float = Field(ge=1)
    minimum_positive_window_ratio: float = Field(ge=0, le=1)
    minimum_positive_years: int = Field(ge=0)
    development_year_count: int = Field(gt=0)
    maximum_drawdown_percent: float = Field(gt=0, le=100)
    maximum_strongest_window_profit_contribution: float = Field(gt=0, le=1)
    require_predefined_cost_stress_pass: bool
    require_tick_replay_pass: bool

    @model_validator(mode="after")
    def validate_year_gate(self) -> PromotionGate:
        if self.minimum_positive_years > self.development_year_count:
            raise ValueError("minimum_positive_years cannot exceed development_year_count")
        return self


class EconomicPromotionGate(StrictModel):
    """Predeclared unit-economics and robustness requirements for new research."""

    gate_schema_version: Literal[2]
    gate_id: str = Field(min_length=1)
    declared_on: date
    provenance_note: str = Field(min_length=1)
    base_cost_model_id: str = Field(min_length=1)
    stress_cost_model_id: str = Field(min_length=1)
    minimum_gross_expectancy_pips: float = Field(gt=0)
    minimum_gross_block_bootstrap_lower_bound_pips: float = Field(ge=0)
    minimum_base_net_expectancy_pips: float = Field(gt=0)
    minimum_stress_net_expectancy_pips: float = Field(gt=0)
    minimum_median_mfe_pips: float = Field(gt=0)
    mfe_exceedance_threshold_pips: float = Field(gt=0)
    minimum_mfe_exceedance_ratio: float = Field(gt=0, le=1)
    minimum_median_mfe_mae_ratio: float = Field(gt=0)
    maximum_base_cost_mfe_ratio: float = Field(gt=0, le=1)
    maximum_stress_cost_mfe_ratio: float = Field(gt=0, le=1)
    minimum_annual_signals: int = Field(gt=0)
    maximum_annual_signals: int = Field(gt=0)
    maximum_entries_per_day: int = Field(gt=0)
    minimum_median_holding_minutes: int = Field(gt=0)
    maximum_median_holding_minutes: int = Field(gt=0)
    hard_maximum_holding_minutes: int = Field(gt=0)
    allow_overnight_positions: bool
    minimum_stop_pips: float = Field(gt=0)
    minimum_stop_stress_cost_multiple: float = Field(gt=0)
    minimum_reward_stress_cost_multiple: float = Field(gt=0)
    minimum_cost_adjusted_reward_risk: float = Field(gt=0)
    bootstrap_confidence_level: float = Field(gt=0, lt=1)
    bootstrap_units: tuple[Literal["day", "week"], ...] = Field(min_length=1)
    minimum_effective_sample_formula: str = Field(min_length=1)
    require_block_bootstrap_pass: bool
    require_effective_sample_size_pass: bool
    require_downside_tail_diagnostic: bool
    minimum_base_profit_factor: float = Field(ge=1)
    minimum_stress_profit_factor: float = Field(ge=1)
    minimum_positive_years: int = Field(ge=0)
    development_year_count: int = Field(gt=0)
    minimum_positive_active_month_ratio: float = Field(ge=0, le=1)
    maximum_drawdown_percent: float = Field(gt=0, le=100)
    maximum_strongest_year_profit_contribution: float = Field(gt=0, le=1)
    maximum_top_decile_trade_profit_contribution: float = Field(gt=0, le=1)
    require_unit_exposure_pass: bool
    require_risk_sized_portfolio_pass: bool
    require_predefined_cost_stress_pass: bool
    require_parameter_neighborhood_pass: bool
    parameter_neighborhood_policy: str = Field(min_length=1)
    require_tick_replay_pass: bool

    @field_validator(
        "minimum_gross_expectancy_pips",
        "minimum_gross_block_bootstrap_lower_bound_pips",
        "minimum_base_net_expectancy_pips",
        "minimum_stress_net_expectancy_pips",
        "minimum_median_mfe_pips",
        "mfe_exceedance_threshold_pips",
        "minimum_mfe_exceedance_ratio",
        "minimum_median_mfe_mae_ratio",
        "maximum_base_cost_mfe_ratio",
        "maximum_stress_cost_mfe_ratio",
        "minimum_stop_pips",
        "minimum_stop_stress_cost_multiple",
        "minimum_reward_stress_cost_multiple",
        "minimum_cost_adjusted_reward_risk",
        "bootstrap_confidence_level",
        "minimum_base_profit_factor",
        "minimum_stress_profit_factor",
        "minimum_positive_active_month_ratio",
        "maximum_drawdown_percent",
        "maximum_strongest_year_profit_contribution",
        "maximum_top_decile_trade_profit_contribution",
    )
    @classmethod
    def finite_thresholds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("promotion thresholds must be finite")
        return value

    @model_validator(mode="after")
    def validate_gate(self) -> EconomicPromotionGate:
        if self.minimum_annual_signals > self.maximum_annual_signals:
            raise ValueError("minimum_annual_signals cannot exceed maximum_annual_signals")
        if self.minimum_median_holding_minutes > self.maximum_median_holding_minutes:
            raise ValueError(
                "minimum_median_holding_minutes cannot exceed maximum_median_holding_minutes"
            )
        if self.maximum_median_holding_minutes > self.hard_maximum_holding_minutes:
            raise ValueError(
                "maximum_median_holding_minutes cannot exceed hard_maximum_holding_minutes"
            )
        if self.minimum_positive_years > self.development_year_count:
            raise ValueError("minimum_positive_years cannot exceed development_year_count")
        if len(self.bootstrap_units) != len(set(self.bootstrap_units)):
            raise ValueError("bootstrap_units must be unique")
        return self


class EvidenceAggregate(StrictModel):
    split: str = Field(min_length=1)
    window_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    net_profit: float
    positive_windows: int = Field(ge=0)
    worst_window_net_profit: float

    @field_validator("net_profit", "worst_window_net_profit")
    @classmethod
    def finite_metrics(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("evidence metrics must be finite")
        return value

    @model_validator(mode="after")
    def validate_window_counts(self) -> EvidenceAggregate:
        if self.positive_windows > self.window_count:
            raise ValueError("positive_windows cannot exceed window_count")
        return self


class ContinuousEvidenceSummary(StrictModel):
    period_start: datetime
    period_end_exclusive: datetime
    trade_count: int = Field(ge=0)
    total_lots: float = Field(ge=0)
    gross_pnl: float
    total_transaction_cost: float = Field(ge=0)
    net_profit: float
    gross_expectancy_per_trade: float | None
    net_expectancy_per_trade: float | None
    profit_factor: float | Literal["infinity"] | None
    max_drawdown: float = Field(ge=0)
    positive_years: int = Field(ge=0)
    year_count: int = Field(gt=0)
    positive_months: int = Field(ge=0)
    month_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_continuous_summary(self) -> ContinuousEvidenceSummary:
        if self.period_start.tzinfo is None or self.period_end_exclusive.tzinfo is None:
            raise ValueError("continuous evidence periods must be timezone-aware")
        if self.period_start >= self.period_end_exclusive:
            raise ValueError("continuous evidence period must be positive")
        if self.positive_years > self.year_count or self.positive_months > self.month_count:
            raise ValueError("positive period counts cannot exceed total period counts")
        numeric = (
            self.total_lots,
            self.gross_pnl,
            self.total_transaction_cost,
            self.net_profit,
            self.gross_expectancy_per_trade,
            self.net_expectancy_per_trade,
            self.max_drawdown,
        )
        if not all(value is None or math.isfinite(value) for value in numeric):
            raise ValueError("continuous evidence metrics must be finite")
        if isinstance(self.profit_factor, float) and not math.isfinite(self.profit_factor):
            raise ValueError("continuous profit_factor must be finite or 'infinity'")
        return self

class ExperimentEvidence(StrictModel):
    experiment_id: str = Field(min_length=1)
    report_path: Path
    cost_model_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    report_run_id: str | None = None
    aggregates: tuple[EvidenceAggregate, ...] = Field(default_factory=tuple)
    continuous_summary: ContinuousEvidenceSummary | None = None
    finding: str = Field(min_length=1)

    @field_validator("report_path")
    @classmethod
    def portable_report_path(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts or value.suffix.lower() != ".json":
            raise ValueError("evidence report_path must be a relative JSON path without '..'")
        return value

    @model_validator(mode="after")
    def validate_result_shape(self) -> ExperimentEvidence:
        splits = [item.split for item in self.aggregates]
        if len(splits) != len(set(splits)):
            raise ValueError("evidence aggregate splits must be unique within an experiment")
        if bool(self.aggregates) == (self.continuous_summary is not None):
            raise ValueError("evidence must contain exactly one of aggregates or continuous_summary")
        if self.continuous_summary is not None and not self.report_run_id:
            raise ValueError("continuous evidence requires report_run_id")
        if self.aggregates and self.report_run_id is not None:
            raise ValueError("fixed-window aggregate evidence cannot set report_run_id")
        return self


class FrozenStrategySpecification(StrictModel):
    """Complete pre-implementation specification for a newly proposed strategy."""

    specification_schema_version: Literal[1] = 1
    market_behavior: str = Field(min_length=1)
    persistence_rationale: str = Field(min_length=1)
    timeframe_hierarchy: tuple[str, ...] = Field(min_length=1)
    session_restrictions: tuple[str, ...] = Field(min_length=1)
    features_and_indicators: tuple[str, ...] = Field(min_length=1)
    lookback_periods: dict[str, Any]
    entry_logic: tuple[str, ...] = Field(min_length=1)
    exit_logic: tuple[str, ...] = Field(min_length=1)
    stop_loss_logic: str = Field(min_length=1)
    take_profit_logic: str = Field(min_length=1)
    time_exit_logic: str = Field(min_length=1)
    maximum_trades_per_day: int = Field(gt=0)
    direction_rules: tuple[str, ...] = Field(min_length=1)
    spread_cost_gate: str = Field(min_length=1)
    expected_minimum_holding_minutes: int = Field(gt=0)
    expected_maximum_holding_minutes: int = Field(gt=0)
    hard_maximum_holding_minutes: int = Field(gt=0)
    allow_overnight_positions: bool
    forbidden_conditions: tuple[str, ...] = Field(min_length=1)

    @field_validator("lookback_periods")
    @classmethod
    def json_lookbacks(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("lookback_periods cannot be empty")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("lookback_periods must contain finite JSON values") from error
        return value

    @model_validator(mode="after")
    def validate_holding_periods(self) -> FrozenStrategySpecification:
        if self.expected_minimum_holding_minutes > self.expected_maximum_holding_minutes:
            raise ValueError(
                "expected_minimum_holding_minutes cannot exceed expected_maximum_holding_minutes"
            )
        if self.expected_maximum_holding_minutes > self.hard_maximum_holding_minutes:
            raise ValueError(
                "expected_maximum_holding_minutes cannot exceed hard_maximum_holding_minutes"
            )
        return self


class StrategyResearchRecord(StrictModel):
    research_id: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    implementation: str | None
    hypothesis: str = Field(min_length=1)
    economic_rationale: str = Field(min_length=1)
    date_proposed: date
    date_provenance: str = Field(min_length=1)
    frozen_rules: tuple[str, ...] = Field(min_length=1)
    frozen_parameters: dict[str, Any]
    frozen_specification: FrozenStrategySpecification | None = None
    permitted_development_dataset_id: str = Field(min_length=1)
    required_broker_cost_model_id: str = Field(min_length=1)
    promotion_gate_id: str = Field(min_length=1)
    experiments_performed: tuple[ExperimentEvidence, ...] = Field(default_factory=tuple)
    status: ResearchStatus
    decision: ResearchDecision
    decision_reason: str = Field(min_length=1)

    @field_validator("implementation")
    @classmethod
    def nonempty_implementation(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("implementation cannot be blank")
        return value

    @field_validator("frozen_parameters")
    @classmethod
    def json_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("frozen_parameters cannot be empty")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("frozen_parameters must contain finite JSON values") from error
        return value

    @model_validator(mode="after")
    def consistent_decision(self) -> StrategyResearchRecord:
        if self.status is ResearchStatus.PROPOSED:
            if self.decision is not ResearchDecision.UNDECIDED:
                raise ValueError("PROPOSED status requires an UNDECIDED decision")
            if self.implementation is not None:
                raise ValueError("PROPOSED status must not claim an implementation")
            if self.experiments_performed:
                raise ValueError("PROPOSED status cannot contain completed experiments")
            if self.frozen_specification is None:
                raise ValueError("PROPOSED status requires a frozen pre-implementation specification")
        elif self.implementation is None:
            raise ValueError("only a PROPOSED strategy may omit its implementation")
        if self.status is ResearchStatus.REJECTED and self.decision is not ResearchDecision.REJECTED:
            raise ValueError("REJECTED status requires a REJECTED decision")
        if self.status is not ResearchStatus.REJECTED and self.decision is ResearchDecision.REJECTED:
            raise ValueError("a REJECTED decision must preserve REJECTED status")
        advanced = {
            ResearchStatus.ROBUSTNESS,
            ResearchStatus.TICK_VALIDATION,
            ResearchStatus.DEMO_ELIGIBLE,
            ResearchStatus.DEMO,
            ResearchStatus.LIVE_ELIGIBLE,
        }
        if self.status in advanced and self.decision is not ResearchDecision.ADVANCE:
            raise ValueError(f"{self.status.value} status requires an ADVANCE decision")
        if self.status not in {ResearchStatus.PROPOSED, ResearchStatus.DEVELOPMENT}:
            if not self.experiments_performed:
                raise ValueError(f"{self.status.value} status requires completed experiment evidence")
        return self

class ResearchRegistry(StrictModel):
    schema_version: int
    registry_id: str = Field(min_length=1)
    updated_at: datetime
    retrospective_registration_notice: str = Field(min_length=1)
    development_datasets: tuple[DevelopmentDataset, ...] = Field(min_length=1)
    broker_cost_models: tuple[BrokerCostModel, ...] = Field(min_length=1)
    promotion_gates: tuple[PromotionGate | EconomicPromotionGate, ...] = Field(min_length=1)
    strategies: tuple[StrategyResearchRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry(self) -> ResearchRegistry:
        if self.schema_version != REGISTRY_SCHEMA_VERSION:
            raise ValueError(f"unsupported registry schema_version: {self.schema_version}")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        datasets = _unique_map(self.development_datasets, "dataset_id")
        costs = _unique_map(self.broker_cost_models, "cost_model_id")
        gates = _unique_map(self.promotion_gates, "gate_id")
        for gate in gates.values():
            if not isinstance(gate, EconomicPromotionGate):
                continue
            if gate.base_cost_model_id not in costs:
                raise ValueError(f"unknown base cost model for promotion gate {gate.gate_id}")
            if gate.stress_cost_model_id not in costs:
                raise ValueError(f"unknown stress cost model for promotion gate {gate.gate_id}")
        _ensure_unique(self.strategies, "research_id")
        _ensure_unique(self.strategies, "strategy_name")
        for record in self.strategies:
            if record.permitted_development_dataset_id not in datasets:
                raise ValueError(f"unknown development dataset for {record.strategy_name}")
            if record.required_broker_cost_model_id not in costs:
                raise ValueError(f"unknown required cost model for {record.strategy_name}")
            if record.promotion_gate_id not in gates:
                raise ValueError(f"unknown promotion gate for {record.strategy_name}")
            gate = gates[record.promotion_gate_id]
            if isinstance(gate, EconomicPromotionGate):
                if record.frozen_specification is None:
                    raise ValueError(
                        f"economic promotion gate requires frozen specification for {record.strategy_name}"
                    )
                if record.required_broker_cost_model_id != gate.base_cost_model_id:
                    raise ValueError(
                        f"required broker cost model must match economic gate base cost model "
                        f"for {record.strategy_name}"
                    )
            elif record.frozen_specification is not None:
                raise ValueError(
                    f"frozen v2 specification requires an economic promotion gate for "
                    f"{record.strategy_name}"
                )
            experiment_ids = [item.experiment_id for item in record.experiments_performed]
            if len(experiment_ids) != len(set(experiment_ids)):
                raise ValueError(f"duplicate experiment_id for {record.strategy_name}")
            for evidence in record.experiments_performed:
                if evidence.cost_model_id not in costs:
                    raise ValueError(f"unknown evidence cost model for {record.strategy_name}")
        return self

    def by_strategy_name(self) -> dict[str, StrategyResearchRecord]:
        return {record.strategy_name: record for record in self.strategies}


def preregistration_fingerprint(registry: ResearchRegistry, strategy_name: str) -> str:
    """Hash the immutable preregistration inputs for a v2 strategy proposal.

    Lifecycle fields are intentionally excluded so implementation, evaluation, and
    the eventual decision can be recorded without changing the frozen research
    fingerprint. Strategy rules, specification, dataset, costs, and promotion gate
    are all included.
    """
    record = registry.by_strategy_name().get(strategy_name)
    if record is None:
        raise RegistryError(f"unknown strategy for preregistration fingerprint: {strategy_name}")
    if record.frozen_specification is None:
        raise RegistryError(f"strategy has no v2 frozen specification: {strategy_name}")
    gates = {item.gate_id: item for item in registry.promotion_gates}
    gate = gates[record.promotion_gate_id]
    if not isinstance(gate, EconomicPromotionGate):
        raise RegistryError(f"strategy has no v2 economic promotion gate: {strategy_name}")
    datasets = {item.dataset_id: item for item in registry.development_datasets}
    costs = {item.cost_model_id: item for item in registry.broker_cost_models}
    payload = {
        "fingerprint_schema_version": 1,
        "strategy": record.model_dump(
            mode="json",
            exclude={
                "implementation",
                "experiments_performed",
                "status",
                "decision",
                "decision_reason",
            },
        ),
        "development_dataset": datasets[
            record.permitted_development_dataset_id
        ].model_dump(mode="json"),
        "base_cost_model": costs[gate.base_cost_model_id].model_dump(mode="json"),
        "stress_cost_model": costs[gate.stress_cost_model_id].model_dump(mode="json"),
        "promotion_gate": gate.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

def load_research_registry(
    path: Path = DEFAULT_REGISTRY_PATH,
    *,
    project_root: Path = Path("."),
    validate_evidence: bool = True,
) -> ResearchRegistry:
    """Load the registry and optionally verify every recorded report aggregate."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        registry = ResearchRegistry.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise RegistryError(f"could not load research registry {path}: {error}") from error
    if validate_evidence:
        _validate_report_evidence(registry, project_root)
    return registry


def record_completed_continuous_experiment(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    report_path: Path,
    experiment_id: str,
    cost_model_id: str,
    role: str,
    findings: Mapping[str, str],
    project_root: Path = Path("."),
    validate_existing_evidence: bool = True,
) -> ResearchRegistry:
    """Atomically attach a completed continuous report to existing strategy records.

    The final report is read-only. Its per-strategy complete summary is copied into
    the registry while the report remains the authoritative detailed evidence.
    Repeating the same registration is idempotent; changing an existing experiment
    ID is rejected.
    """
    if not experiment_id or not role or not findings:
        raise RegistryError("continuous experiment metadata and findings cannot be empty")
    root = project_root.resolve()
    resolved_report = report_path.resolve() if report_path.is_absolute() else (root / report_path).resolve()
    try:
        portable_report = resolved_report.relative_to(root)
    except ValueError as error:
        raise RegistryError("continuous report must be inside project_root") from error
    if resolved_report.name.endswith(".checkpoint.json"):
        raise RegistryError("a running checkpoint cannot be registered as a completed experiment")
    try:
        report = json.loads(resolved_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"could not read completed continuous report {resolved_report}: {error}") from error
    if not isinstance(report, dict):
        raise RegistryError("continuous report root must be a JSON object")

    registry = load_research_registry(
        registry_path,
        project_root=root,
        validate_evidence=validate_existing_evidence,
    )
    by_name = registry.by_strategy_name()
    unknown = set(findings).difference(by_name)
    if unknown:
        raise RegistryError(f"continuous report registration names unknown strategies: {sorted(unknown)}")
    cost_models = {item.cost_model_id: item for item in registry.broker_cost_models}
    datasets = {item.dataset_id: item for item in registry.development_datasets}
    if cost_model_id not in cost_models:
        raise RegistryError(f"continuous experiment references unknown cost model: {cost_model_id}")
    _validate_report_costs(report, cost_models[cost_model_id], resolved_report)
    manifest = report.get("run_manifest")
    run_id = manifest.get("run_id") if isinstance(manifest, dict) else report.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise RegistryError("completed continuous report has no run_manifest.run_id")

    updated_records: list[StrategyResearchRecord] = []
    changed = False
    for record in registry.strategies:
        if record.strategy_name not in findings:
            updated_records.append(record)
            continue
        result = _continuous_result(report, record.strategy_name, resolved_report)
        summary = _continuous_summary_from_result(result, record.strategy_name, resolved_report)
        _validate_continuous_period(
            summary, datasets[record.permitted_development_dataset_id], record.strategy_name
        )
        evidence = ExperimentEvidence(
            experiment_id=experiment_id,
            report_path=portable_report,
            cost_model_id=cost_model_id,
            role=role,
            report_run_id=run_id,
            continuous_summary=summary,
            finding=findings[record.strategy_name],
        )
        existing = [item for item in record.experiments_performed if item.experiment_id == experiment_id]
        if existing:
            if existing[0] != evidence:
                raise RegistryError(
                    f"experiment_id {experiment_id!r} already records different evidence for {record.strategy_name}"
                )
            updated_records.append(record)
            continue
        changed = True
        updated_records.append(
            StrategyResearchRecord.model_validate({
                **record.model_dump(mode="python"),
                "experiments_performed": [*record.experiments_performed, evidence],
            })
        )

    if not changed:
        return registry

    updated = ResearchRegistry.model_validate({
        **registry.model_dump(mode="python"),
        "updated_at": datetime.now(UTC),
        "strategies": updated_records,
    })
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = registry_path.with_name(f".{registry_path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(updated.model_dump(mode="json"), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(registry_path)
    except OSError as error:
        raise RegistryError(f"could not atomically update research registry {registry_path}: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()
    return load_research_registry(
        registry_path,
        project_root=root,
        validate_evidence=validate_existing_evidence,
    )

def reject_strategy_after_completed_evidence(
    strategy_name: str,
    reason: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    project_root: Path = Path("."),
) -> ResearchRegistry:
    """Atomically close an undecided development strategy with validated evidence."""

    if not strategy_name.strip() or not reason.strip():
        raise RegistryError("strategy name and rejection reason cannot be empty")
    root = project_root.resolve()
    registry = load_research_registry(
        registry_path,
        project_root=root,
        validate_evidence=True,
    )
    record = registry.by_strategy_name().get(strategy_name)
    if record is None:
        raise RegistryError(f"unknown strategy for rejection: {strategy_name}")
    if record.status is ResearchStatus.REJECTED:
        if record.decision_reason != reason:
            raise RegistryError("strategy is already rejected with a different reason")
        return registry
    if (
        record.status is not ResearchStatus.DEVELOPMENT
        or record.decision is not ResearchDecision.UNDECIDED
    ):
        raise RegistryError("only an undecided DEVELOPMENT strategy may be rejected")
    if not record.experiments_performed:
        raise RegistryError("completed experiment evidence is required before rejection")

    updated_records = [
        StrategyResearchRecord.model_validate(
            {
                **item.model_dump(mode="python"),
                "status": ResearchStatus.REJECTED,
                "decision": ResearchDecision.REJECTED,
                "decision_reason": reason,
            }
        )
        if item.strategy_name == strategy_name
        else item
        for item in registry.strategies
    ]
    updated = ResearchRegistry.model_validate(
        {
            **registry.model_dump(mode="python"),
            "updated_at": datetime.now(UTC),
            "strategies": updated_records,
        }
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = registry_path.with_name(f".{registry_path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(updated.model_dump(mode="json"), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(registry_path)
    except OSError as error:
        raise RegistryError(f"could not atomically update research registry {registry_path}: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()
    return load_research_registry(
        registry_path,
        project_root=root,
        validate_evidence=True,
    )

def _validate_report_evidence(registry: ResearchRegistry, project_root: Path) -> None:
    cost_models = {item.cost_model_id: item for item in registry.broker_cost_models}
    datasets = {item.dataset_id: item for item in registry.development_datasets}
    cache: dict[Path, dict[str, Any]] = {}
    for record in registry.strategies:
        for evidence in record.experiments_performed:
            report_path = project_root / evidence.report_path
            if report_path not in cache:
                try:
                    loaded = json.loads(report_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise RegistryError(f"could not read registry evidence {report_path}: {error}") from error
                if not isinstance(loaded, dict):
                    raise RegistryError(f"registry evidence root is not an object: {report_path}")
                cache[report_path] = loaded
            report = cache[report_path]
            _validate_report_costs(report, cost_models[evidence.cost_model_id], report_path)
            if evidence.continuous_summary is not None:
                result = _continuous_result(report, record.strategy_name, report_path)
                actual_summary = _continuous_summary_from_result(result, record.strategy_name, report_path)
                _validate_continuous_period(
                    actual_summary,
                    datasets[record.permitted_development_dataset_id],
                    record.strategy_name,
                )
                manifest = report.get("run_manifest")
                actual_run_id = manifest.get("run_id") if isinstance(manifest, dict) else report.get("run_id")
                if actual_run_id != evidence.report_run_id:
                    raise RegistryError(f"continuous evidence run_id mismatch for {record.strategy_name}")
                if actual_summary != evidence.continuous_summary:
                    raise RegistryError(f"continuous evidence summary mismatch for {record.strategy_name}")
                continue
            aggregates = report.get("aggregates")
            if not isinstance(aggregates, list):
                raise RegistryError(f"registry evidence has no aggregate list: {report_path}")
            for expected in evidence.aggregates:
                matches = [
                    item for item in aggregates
                    if isinstance(item, dict)
                    and item.get("strategy") == record.strategy_name
                    and item.get("split") == expected.split
                ]
                if len(matches) != 1:
                    raise RegistryError(
                        f"expected one {record.strategy_name}/{expected.split} aggregate in {report_path}"
                    )
                actual = matches[0]
                for field, expected_value in expected.model_dump().items():
                    actual_value = actual.get(field)
                    if isinstance(expected_value, float):
                        if not isinstance(actual_value, (int, float)) or not math.isclose(
                            float(actual_value), expected_value, rel_tol=1e-12, abs_tol=1e-9
                        ):
                            raise RegistryError(
                                f"evidence mismatch for {record.strategy_name}/{expected.split}/{field}"
                            )
                    elif actual_value != expected_value:
                        raise RegistryError(
                            f"evidence mismatch for {record.strategy_name}/{expected.split}/{field}"
                        )


def _continuous_result(report: dict[str, Any], strategy_name: str, path: Path) -> dict[str, Any]:
    if report.get("strategy") == strategy_name and isinstance(report.get("summaries"), dict):
        matches = [report]
    else:
        results = report.get("results")
        if not isinstance(results, list):
            raise RegistryError(f"continuous report has no results list: {path}")
        matches = [
            item for item in results
            if isinstance(item, dict) and item.get("strategy") == strategy_name
        ]
    if len(matches) != 1:
        raise RegistryError(f"expected one continuous result for {strategy_name} in {path}")
    result = matches[0]
    period = result.get("period")
    if (
        not isinstance(period, dict)
        or period.get("name") != "development"
        or period.get("end_exclusive") is not True
        or period.get("post_selection_data_used") is not False
    ):
        raise RegistryError(f"continuous result is not isolated development evidence for {strategy_name}")
    return result


def _continuous_summary_from_result(
    result: dict[str, Any], strategy_name: str, path: Path
) -> ContinuousEvidenceSummary:
    try:
        period = result["period"]
        summaries = result["summaries"]
        complete = summaries["complete"]
        by_year = summaries["by_year"]
        by_month = summaries["by_month"]
        if not isinstance(period, dict) or not isinstance(complete, dict):
            raise TypeError("period and complete summary must be objects")
        if not isinstance(by_year, list) or not isinstance(by_month, list):
            raise TypeError("year and month summaries must be arrays")
        return ContinuousEvidenceSummary(
            period_start=period["start"],
            period_end_exclusive=period["end"],
            trade_count=complete["trade_count"],
            total_lots=complete["total_lots"],
            gross_pnl=complete["gross_pnl"],
            total_transaction_cost=complete["total_transaction_cost"],
            net_profit=complete["net_profit"],
            gross_expectancy_per_trade=complete["gross_expectancy_per_trade"],
            net_expectancy_per_trade=complete["net_expectancy_per_trade"],
            profit_factor=complete["profit_factor"],
            max_drawdown=complete["max_drawdown"],
            positive_years=_positive_period_count(by_year),
            year_count=len(by_year),
            positive_months=_positive_period_count(by_month),
            month_count=len(by_month),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise RegistryError(
            f"continuous summary for {strategy_name} is incomplete or invalid in {path}: {error}"
        ) from error


def _validate_continuous_period(
    summary: ContinuousEvidenceSummary,
    dataset: DevelopmentDataset,
    strategy_name: str,
) -> None:
    start = summary.period_start.astimezone(UTC)
    end = summary.period_end_exclusive.astimezone(UTC)
    if (
        start.date() != dataset.start
        or start.time() != datetime.min.time()
        or end.date() != dataset.end_exclusive
        or end.time() != datetime.min.time()
    ):
        raise RegistryError(
            f"continuous evidence period does not match permitted development dataset for {strategy_name}"
        )

def _positive_period_count(rows: Sequence[object]) -> int:
    positive = 0
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("period summary row must be an object")
        net_profit = row.get("net_profit")
        if not isinstance(net_profit, (int, float)) or not math.isfinite(float(net_profit)):
            raise ValueError("period net_profit must be finite")
        positive += float(net_profit) > 0
    return positive

def _validate_report_costs(report: dict[str, Any], model: BrokerCostModel, path: Path) -> None:
    assumptions = report.get("backtest_assumptions")
    if not isinstance(assumptions, dict):
        raise RegistryError(f"registry evidence has no backtest_assumptions: {path}")
    expected = {
        "spread_points": model.spread_points,
        "slippage_points": model.slippage_points,
        "commission_per_lot_per_side": model.commission_per_lot_per_side,
    }
    for field, value in expected.items():
        actual = assumptions.get(field)
        if not isinstance(actual, (int, float)) or not math.isclose(float(actual), value, abs_tol=1e-12):
            raise RegistryError(f"evidence cost mismatch for {field} in {path}")


def _unique_map(items: tuple[StrictModel, ...], field: str) -> dict[str, StrictModel]:
    _ensure_unique(items, field)
    return {str(getattr(item, field)): item for item in items}


def _ensure_unique(items: tuple[StrictModel, ...], field: str) -> None:
    values = [getattr(item, field) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"registry {field} values must be unique")
