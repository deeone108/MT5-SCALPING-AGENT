from __future__ import annotations

import json
from pathlib import Path

import pytest

from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.research.registry import (
    DEFAULT_REGISTRY_PATH,
    EconomicPromotionGate,
    RegistryError,
    ResearchDecision,
    ResearchStatus,
    load_research_registry,
    preregistration_fingerprint,
    reject_strategy_after_completed_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / DEFAULT_REGISTRY_PATH
STRATEGY_15_NAME = "compression_expansion_controlled_continuation"
STRATEGY_15_PREREGISTRATION_FINGERPRINT = (
    "sha256:ea560ec22b835bd1010602ca419843c584adde33b73b9cb433984cc0b5249ff6"
)


STRATEGY_16_NAME = "scheduled_us_macro_shock_continuation"
STRATEGY_16_PREREGISTRATION_FINGERPRINT = (
    "sha256:758806be23c4388df121bf0ddc2f7465b6e31375a61a735f6c9eb7d3654ff606"
)

def _payload() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "research_registry.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_default_registry_preserves_all_current_implemented_strategies() -> None:
    registry = load_research_registry(REGISTRY_PATH, project_root=PROJECT_ROOT)
    by_name = registry.by_strategy_name()
    implemented = {record.strategy_name for record in registry.strategies if record.implementation}

    assert len(STRATEGIES) == 14
    assert set(STRATEGIES).issubset(implemented)
    assert implemented == {*STRATEGIES, STRATEGY_15_NAME, STRATEGY_16_NAME}
    for name, strategy_type in STRATEGIES.items():
        record = by_name[name]
        assert record.status is ResearchStatus.REJECTED
        assert record.decision is ResearchDecision.REJECTED
        assert record.implementation == f"{strategy_type.__module__}.{strategy_type.__qualname__}"
    strategy_15 = by_name[STRATEGY_15_NAME]
    assert strategy_15.status is ResearchStatus.REJECTED
    assert strategy_15.decision is ResearchDecision.REJECTED
    assert strategy_15.implementation == (
        "mt5_scalping_agent.backtesting.compression_expansion_continuation."
        "CompressionExpansionControlledContinuationStrategy"
    )
    assert len(strategy_15.experiments_performed) == 2
    strategy_16 = by_name[STRATEGY_16_NAME]
    assert strategy_16.status is ResearchStatus.REJECTED
    assert strategy_16.decision is ResearchDecision.REJECTED
    assert strategy_16.implementation == (
        "mt5_scalping_agent.backtesting.scheduled_macro_shock."
        "ScheduledMacroShockContinuationStrategy"
    )
    assert len(strategy_16.experiments_performed) == 2
def test_registry_preserves_frozen_research_inputs_and_future_gates() -> None:
    registry = load_research_registry(REGISTRY_PATH, project_root=PROJECT_ROOT)
    dataset = registry.development_datasets[0]
    gate = registry.promotion_gates[0]
    by_name = registry.by_strategy_name()

    assert dataset.start.isoformat() == "2019-01-01"
    assert dataset.end_exclusive.isoformat() == "2024-01-01"
    assert dataset.excluded_from_tuning == ("2024", "2025", "2026")
    assert gate.minimum_development_trades == 300
    assert gate.minimum_positive_window_ratio == 0.6
    assert "after existing experiments" in gate.provenance_note
    for name in STRATEGIES:
        record = by_name[name]
        assert record.frozen_rules
        assert record.frozen_parameters
        assert record.experiments_performed
        assert record.permitted_development_dataset_id == dataset.dataset_id
        assert record.required_broker_cost_model_id == "roboforex_ecn_eurusd_v1"
        assert record.promotion_gate_id == gate.gate_id

    strategy_15 = by_name[STRATEGY_15_NAME]
    proposal_gate = next(
        item for item in registry.promotion_gates if item.gate_id == strategy_15.promotion_gate_id
    )
    assert strategy_15.research_id == "strategy_15_compression_expansion_controlled_continuation_v1"
    assert strategy_15.status is ResearchStatus.REJECTED
    assert strategy_15.decision is ResearchDecision.REJECTED
    assert strategy_15.implementation is not None
    assert len(strategy_15.experiments_performed) == 2
    assert strategy_15.frozen_specification is not None
    assert isinstance(proposal_gate, EconomicPromotionGate)
    assert proposal_gate.base_cost_model_id == "roboforex_ecn_eurusd_v1"
    assert proposal_gate.stress_cost_model_id == "roboforex_ecn_eurusd_stress_v1"


def test_evidence_backed_rejection_transition_is_atomic(tmp_path: Path) -> None:
    payload = _payload()
    strategy = next(
        item for item in payload["strategies"] if item["strategy_name"] == STRATEGY_15_NAME
    )
    strategy["status"] = "DEVELOPMENT"
    strategy["decision"] = "UNDECIDED"
    strategy["decision_reason"] = "Evaluation pending."
    path = _write_payload(tmp_path, payload)

    reason = "Frozen development gates failed; no robustness evaluation was eligible."
    updated = reject_strategy_after_completed_evidence(
        STRATEGY_15_NAME,
        reason,
        registry_path=path,
        project_root=PROJECT_ROOT,
    )

    record = updated.by_strategy_name()[STRATEGY_15_NAME]
    assert record.status is ResearchStatus.REJECTED
    assert record.decision is ResearchDecision.REJECTED
    assert record.decision_reason == reason
    assert len(record.experiments_performed) == 2

def test_strategy_16_preregistration_fingerprint_is_frozen() -> None:
    registry = load_research_registry(REGISTRY_PATH, project_root=PROJECT_ROOT)
    record = registry.by_strategy_name()[STRATEGY_16_NAME]

    assert len(registry.strategies) == 17
    assert record.status is ResearchStatus.REJECTED
    assert record.decision is ResearchDecision.REJECTED
    assert len(record.experiments_performed) == 2
    assert preregistration_fingerprint(registry, STRATEGY_16_NAME) == (
        STRATEGY_16_PREREGISTRATION_FINGERPRINT
    )

def test_registry_rejects_duplicate_research_ids(tmp_path: Path) -> None:
    payload = _payload()
    strategies = payload["strategies"]
    strategies[1]["research_id"] = strategies[0]["research_id"]  # type: ignore[index]

    with pytest.raises(RegistryError, match="research_id.*unique"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_registry_rejects_status_decision_inconsistency(tmp_path: Path) -> None:
    payload = _payload()
    payload["strategies"][0]["status"] = "DEVELOPMENT"  # type: ignore[index]

    with pytest.raises(RegistryError, match="REJECTED decision must preserve REJECTED status"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_registry_rejects_unknown_policy_reference(tmp_path: Path) -> None:
    payload = _payload()
    payload["strategies"][0]["promotion_gate_id"] = "missing_gate"  # type: ignore[index]

    with pytest.raises(RegistryError, match="unknown promotion gate"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_registry_detects_evidence_metric_drift(tmp_path: Path) -> None:
    payload = _payload()
    payload["strategies"][0]["experiments_performed"][0]["aggregates"][0]["net_profit"] = 999.0  # type: ignore[index]

    with pytest.raises(RegistryError, match="evidence mismatch.*net_profit"):
        load_research_registry(
            _write_payload(tmp_path, payload),
            project_root=PROJECT_ROOT,
            validate_evidence=True,
        )


def test_registry_requires_existing_evidence_report(tmp_path: Path) -> None:
    payload = _payload()
    payload["strategies"][0]["experiments_performed"][0]["report_path"] = "reports/missing.json"  # type: ignore[index]

    with pytest.raises(RegistryError, match="could not read registry evidence"):
        load_research_registry(
            _write_payload(tmp_path, payload),
            project_root=PROJECT_ROOT,
            validate_evidence=True,
        )


def test_status_enum_supports_full_research_lifecycle() -> None:
    assert {status.value for status in ResearchStatus} == {
        "PROPOSED",
        "DEVELOPMENT",
        "REJECTED",
        "ROBUSTNESS",
        "TICK_VALIDATION",
        "DEMO_ELIGIBLE",
        "DEMO",
        "LIVE_ELIGIBLE",
    }


def _future_proposal_payload() -> dict[str, object]:
    payload = _payload()
    cost_models = payload["broker_cost_models"]  # type: ignore[assignment]
    if not any(
        item["cost_model_id"] == "roboforex_ecn_eurusd_stress_v1" for item in cost_models
    ):
        cost_models.append(
            {
                "cost_model_id": "roboforex_ecn_eurusd_stress_v1",
                "broker": "RoboForex Ltd",
                "account_type": "RoboForex-ECN research stress",
                "symbol": "EURUSD",
                "point_size": 0.00001,
                "spread_points": 4.0,
                "slippage_points": 2.0,
                "commission_per_lot_per_side": 2.0,
                "currency": "USD",
                "calibration_evidence": "Predeclared stress scenario fixture.",
            }
        )
    payload["promotion_gates"].append(  # type: ignore[union-attr]
        {
            "gate_schema_version": 2,
            "gate_id": "future_candidate_economic_gate_v2",
            "declared_on": "2026-08-24",
            "provenance_note": "Predeclared before implementation and development evaluation.",
            "base_cost_model_id": "roboforex_ecn_eurusd_v1",
            "stress_cost_model_id": "roboforex_ecn_eurusd_stress_v1",
            "minimum_gross_expectancy_pips": 1.5,
            "minimum_gross_block_bootstrap_lower_bound_pips": 1.0,
            "minimum_base_net_expectancy_pips": 0.8,
            "minimum_stress_net_expectancy_pips": 0.5,
            "minimum_median_mfe_pips": 4.0,
            "mfe_exceedance_threshold_pips": 3.0,
            "minimum_mfe_exceedance_ratio": 0.6,
            "minimum_median_mfe_mae_ratio": 1.5,
            "maximum_base_cost_mfe_ratio": 0.2,
            "maximum_stress_cost_mfe_ratio": 0.25,
            "minimum_annual_signals": 250,
            "maximum_annual_signals": 500,
            "maximum_entries_per_day": 2,
            "minimum_median_holding_minutes": 15,
            "maximum_median_holding_minutes": 120,
            "hard_maximum_holding_minutes": 240,
            "allow_overnight_positions": False,
            "minimum_stop_pips": 4.0,
            "minimum_stop_stress_cost_multiple": 4.0,
            "minimum_reward_stress_cost_multiple": 6.0,
            "minimum_cost_adjusted_reward_risk": 1.5,
            "bootstrap_confidence_level": 0.95,
            "bootstrap_units": ["day", "week"],
            "minimum_effective_sample_formula": (
                "ceil(((1.96 + 0.84) * s_net / 0.5)^2)"
            ),
            "require_block_bootstrap_pass": True,
            "require_effective_sample_size_pass": True,
            "require_downside_tail_diagnostic": True,
            "minimum_base_profit_factor": 1.25,
            "minimum_stress_profit_factor": 1.1,
            "minimum_positive_years": 4,
            "development_year_count": 5,
            "minimum_positive_active_month_ratio": 0.55,
            "maximum_drawdown_percent": 10.0,
            "maximum_strongest_year_profit_contribution": 0.35,
            "maximum_top_decile_trade_profit_contribution": 0.5,
            "require_unit_exposure_pass": True,
            "require_risk_sized_portfolio_pass": True,
            "require_predefined_cost_stress_pass": True,
            "require_parameter_neighborhood_pass": True,
            "parameter_neighborhood_policy": (
                "Use only predeclared adjacent cases for fragility detection; never select a winner."
            ),
            "require_tick_replay_pass": True,
        }
    )
    payload["strategies"].append(  # type: ignore[union-attr]
        {
            "research_id": "schema_fixture_candidate_v1",
            "strategy_name": "schema_fixture_candidate",
            "implementation": None,
            "hypothesis": "A distinct structural setup may produce infrequent large moves.",
            "economic_rationale": "Expected movement must materially exceed modeled friction.",
            "date_proposed": "2026-08-24",
            "date_provenance": "Test fixture declared before implementation.",
            "frozen_rules": ["Use completed bars only.", "Emit at most two intents daily."],
            "frozen_parameters": {"compression_lookback": 60, "maximum_trades_per_day": 2},
            "frozen_specification": {
                "specification_schema_version": 1,
                "market_behavior": "Compression followed by expansion and continuation.",
                "persistence_rationale": "Liquidity transitions may recur across regimes.",
                "timeframe_hierarchy": ["M1 execution", "M5 context"],
                "session_restrictions": ["DST-aware New York morning only"],
                "features_and_indicators": ["completed-bar range compression"],
                "lookback_periods": {"compression_bars": 60, "context_bars": 24},
                "entry_logic": ["Wait for a completed expansion and causal continuation."],
                "exit_logic": ["Exit at stop, target, or the hard time limit."],
                "stop_loss_logic": "Use a structural stop of at least four pips.",
                "take_profit_logic": "Require planned reward of at least six stress costs.",
                "time_exit_logic": "Exit intraday by 240 minutes.",
                "maximum_trades_per_day": 2,
                "direction_rules": ["Allow long and short only with aligned context."],
                "spread_cost_gate": "Reject when remaining reward is economically cramped.",
                "expected_minimum_holding_minutes": 15,
                "expected_maximum_holding_minutes": 120,
                "hard_maximum_holding_minutes": 240,
                "allow_overnight_positions": False,
                "forbidden_conditions": ["No incomplete bars or post-period data."],
            },
            "permitted_development_dataset_id": (
                "dukascopy_eurusd_m1_development_2019_2023"
            ),
            "required_broker_cost_model_id": "roboforex_ecn_eurusd_v1",
            "promotion_gate_id": "future_candidate_economic_gate_v2",
            "experiments_performed": [],
            "status": "PROPOSED",
            "decision": "UNDECIDED",
            "decision_reason": "Awaiting implementation and development evaluation.",
        }
    )
    return payload


def test_v2_accepts_honest_unimplemented_proposal_without_evidence(tmp_path: Path) -> None:
    registry = load_research_registry(
        _write_payload(tmp_path, _future_proposal_payload()),
        validate_evidence=False,
    )

    record = registry.by_strategy_name()["schema_fixture_candidate"]
    gate = next(item for item in registry.promotion_gates if item.gate_id == record.promotion_gate_id)
    assert registry.schema_version == 2
    assert record.status is ResearchStatus.PROPOSED
    assert record.decision is ResearchDecision.UNDECIDED
    assert record.implementation is None
    assert record.experiments_performed == ()
    assert record.frozen_specification is not None
    assert isinstance(gate, EconomicPromotionGate)
    assert gate.minimum_stress_net_expectancy_pips == 0.5
    assert gate.bootstrap_units == ("day", "week")


def test_proposed_record_rejects_claimed_implementation(tmp_path: Path) -> None:
    payload = _future_proposal_payload()
    payload["strategies"][-1]["implementation"] = "package.UnrunStrategy"  # type: ignore[index]

    with pytest.raises(RegistryError, match="PROPOSED status must not claim an implementation"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_proposed_record_rejects_completed_evidence(tmp_path: Path) -> None:
    payload = _future_proposal_payload()
    payload["strategies"][-1]["experiments_performed"] = [  # type: ignore[index]
        payload["strategies"][0]["experiments_performed"][0]  # type: ignore[index]
    ]

    with pytest.raises(RegistryError, match="PROPOSED status cannot contain completed experiments"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_terminal_status_still_requires_evidence(tmp_path: Path) -> None:
    payload = _payload()
    payload["strategies"][0]["experiments_performed"] = []  # type: ignore[index]

    with pytest.raises(RegistryError, match="REJECTED status requires completed experiment evidence"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_economic_gate_rejects_unknown_stress_cost_model(tmp_path: Path) -> None:
    payload = _future_proposal_payload()
    payload["promotion_gates"][-1]["stress_cost_model_id"] = "missing"  # type: ignore[index]

    with pytest.raises(RegistryError, match="unknown stress cost model"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)


def test_registry_rejects_unmigrated_root_schema(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema_version"] = 1

    with pytest.raises(RegistryError, match="unsupported registry schema_version: 1"):
        load_research_registry(_write_payload(tmp_path, payload), validate_evidence=False)

def test_strategy_15_preregistration_fingerprint_is_frozen_and_lifecycle_stable(
    tmp_path: Path,
) -> None:
    registry = load_research_registry(REGISTRY_PATH, validate_evidence=False)

    assert preregistration_fingerprint(registry, STRATEGY_15_NAME) == (
        STRATEGY_15_PREREGISTRATION_FINGERPRINT
    )

    lifecycle_payload = _payload()
    lifecycle_record = next(
        item for item in lifecycle_payload["strategies"] if item["strategy_name"] == STRATEGY_15_NAME
    )  # type: ignore[index, union-attr]
    lifecycle_record["implementation"] = "package.CompressionExpansionStrategy"
    lifecycle_record["status"] = "DEVELOPMENT"
    lifecycle_record["decision"] = "UNDECIDED"
    lifecycle_record["experiments_performed"] = []
    lifecycle_record["decision_reason"] = "Implementation complete; evaluation pending."
    lifecycle_registry = load_research_registry(
        _write_payload(tmp_path, lifecycle_payload),
        validate_evidence=False,
    )
    assert preregistration_fingerprint(lifecycle_registry, STRATEGY_15_NAME) == (
        STRATEGY_15_PREREGISTRATION_FINGERPRINT
    )

    changed_payload = _payload()
    changed_record = next(
        item for item in changed_payload["strategies"] if item["strategy_name"] == STRATEGY_15_NAME
    )  # type: ignore[index, union-attr]
    changed_record["hypothesis"] += " Substantive mutation."
    changed_registry = load_research_registry(
        _write_payload(tmp_path, changed_payload),
        validate_evidence=False,
    )
    assert preregistration_fingerprint(changed_registry, STRATEGY_15_NAME) != (
        STRATEGY_15_PREREGISTRATION_FINGERPRINT
    )