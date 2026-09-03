"""One-time prospective Strategy 17 intraday-pivot registration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.research.registry import ResearchRegistry


REGISTRY_PATH = Path("config/research_registry.json")
STRATEGY_NAME = "london_new_york_intraday_continuation"


def main() -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if any(item["strategy_name"] == STRATEGY_NAME for item in payload["strategies"]):
        raise SystemExit("Strategy 17 is already registered; frozen inputs cannot be rewritten")
    payload["broker_cost_models"].extend((
        {"cost_model_id": "roboforex_ecn_eurusd_intraday_base_v1", "broker": "RoboForex Ltd", "account_type": "RoboForex-ECN demo normal-session intraday research", "symbol": "EURUSD", "point_size": 0.00001, "spread_points": 1.0, "slippage_points": 1.0, "commission_per_lot_per_side": 2.0, "currency": "USD", "calibration_evidence": "Predeclared normal-session base from the RoboForex London/New York captures; one-point slippage remains a conservative assumption."},
        {"cost_model_id": "roboforex_ecn_eurusd_intraday_stress_v1", "broker": "RoboForex Ltd", "account_type": "RoboForex-ECN demo normal-session intraday stress", "symbol": "EURUSD", "point_size": 0.00001, "spread_points": 3.0, "slippage_points": 2.0, "commission_per_lot_per_side": 2.0, "currency": "USD", "calibration_evidence": "Predeclared normal-session intraday stress, deliberately above observed p95 spread; not a historical execution replay."},
    ))
    payload["promotion_gates"].append({
        "gate_schema_version": 2, "gate_id": "strategy_17_intraday_economic_gate_v1", "declared_on": "2026-08-30",
        "provenance_note": "Prospectively frozen in docs/STRATEGY_17_RESEARCH_BRIEF.md before implementation or Strategy 17 development-data access.",
        "base_cost_model_id": "roboforex_ecn_eurusd_intraday_base_v1", "stress_cost_model_id": "roboforex_ecn_eurusd_intraday_stress_v1",
        "minimum_gross_expectancy_pips": 5.0, "minimum_gross_block_bootstrap_lower_bound_pips": 2.5, "minimum_base_net_expectancy_pips": 4.0, "minimum_stress_net_expectancy_pips": 3.0,
        "minimum_median_mfe_pips": 20.0, "mfe_exceedance_threshold_pips": 12.0, "minimum_mfe_exceedance_ratio": 0.65, "minimum_median_mfe_mae_ratio": 1.5,
        "maximum_base_cost_mfe_ratio": 0.05, "maximum_stress_cost_mfe_ratio": 0.08, "minimum_annual_signals": 40, "maximum_annual_signals": 160,
        "maximum_entries_per_day": 1, "minimum_median_holding_minutes": 60, "maximum_median_holding_minutes": 240, "hard_maximum_holding_minutes": 300, "allow_overnight_positions": False,
        "minimum_stop_pips": 12.0, "minimum_stop_stress_cost_multiple": 10.0, "minimum_reward_stress_cost_multiple": 30.0, "minimum_cost_adjusted_reward_risk": 1.5,
        "bootstrap_confidence_level": 0.95, "bootstrap_units": ["day", "week"], "minimum_effective_sample_formula": "ceil(((1.96 + 0.84) * sample_standard_deviation_of_stress_net_pips / 3.0)^2)",
        "require_block_bootstrap_pass": True, "require_effective_sample_size_pass": True, "require_downside_tail_diagnostic": True, "minimum_base_profit_factor": 1.35, "minimum_stress_profit_factor": 1.20,
        "minimum_positive_years": 4, "development_year_count": 5, "minimum_positive_active_month_ratio": 0.55, "maximum_drawdown_percent": 10.0, "maximum_strongest_year_profit_contribution": 0.40, "maximum_top_decile_trade_profit_contribution": 0.50,
        "require_unit_exposure_pass": True, "require_risk_sized_portfolio_pass": True, "require_predefined_cost_stress_pass": True, "require_parameter_neighborhood_pass": True,
        "parameter_neighborhood_policy": "Only after all primary gates pass, run frozen one-factor neighbours for impulse 22/28 pips, pullback 0.35/0.45, reclaim 0.75/0.85, target 1.75/2.25R, and stop buffer 0.5/1.5 pips. Every case must have positive stress expectancy; at least 8/10 must retain gross >=5 and stress net >=3 pips. Never select a neighbour.",
        "require_tick_replay_pass": True,
    })
    rules = (
        "Use only validated UTC EURUSD bid M1 OHLCV converted with Europe/London zoneinfo; Monday-Friday only.",
        "At 11:00 London require every exact M1 candle from 06:00 through 11:00 and derive completed hourly impulse/pullback composites causally.",
        "Require 06:00-10:00 directional impulse >=25 pips, efficiency >=0.60, 10:00-11:00 pullback <=40% of impulse, and 11:00 close retaining >=80% of impulse.",
        "Enter only at exact next M1 open at 11:01; emit at most one intent per London date and a rejected intent consumes its date.",
        "Use pullback extreme plus one pip as stop; actual risk 12-35 pips; target exactly 2R from actual entry and at least 30 pips reward.",
        "Exit at stop or target, otherwise first M1 close at or after 16:00 London, no later than 300 minutes and never overnight.",
        "Do not use calendars, volume, order flow, future prices, pyramiding, averaging, partial exits, trailing, break-even moves, concurrent positions, or discretionary handling.",
    )
    params = {"timezone": "Europe/London", "required_start_local": "06:00", "signal_time_local": "11:00", "entry_time_local": "11:01", "hard_exit_time_local": "16:00", "impulse_hours": 4, "pullback_hours": 1, "minimum_impulse_pips": 25.0, "minimum_impulse_efficiency": 0.60, "maximum_pullback_fraction": 0.40, "minimum_reclaim_fraction": 0.80, "stop_buffer_pips": 1.0, "minimum_stop_pips": 12.0, "maximum_stop_pips": 35.0, "target_reward_risk_multiple": 2.0, "minimum_reward_pips": 30.0, "maximum_holding_minutes": 300, "maximum_emitted_signals_per_london_day": 1, "unit_exposure_model": {"fixed_volume_lots": 1.0, "initial_equity_usd": 10000.0}}
    specification = {"specification_schema_version": 1, "market_behavior": "London directional price discovery persisting into the New York overlap after a shallow contained pullback.", "persistence_rationale": "A multi-hour impulse and retained reclaim seek residual intraday order-flow adjustment with a planned reward far larger than normal-session friction.", "timeframe_hierarchy": ["UTC M1 execution", "completed London civil-time hourly composites"], "session_restrictions": ["Monday-Friday London dates", "only 11:00 signal and 11:01 entry", "16:00 hard exit"], "features_and_indicators": ["four-hour signed impulse", "impulse high-low efficiency", "one-hour pullback magnitude", "reclaimed impulse fraction"], "lookback_periods": {"M1_minutes": 301, "impulse_hours": 4, "pullback_hours": 1}, "entry_logic": ["Require every frozen impulse, efficiency, pullback, and reclaim condition at 11:00.", "Enter only on the exact next M1 open."], "exit_logic": ["Full stop or fixed target.", "Otherwise hard exit at 16:00 London."], "stop_loss_logic": "Pullback extreme plus one pip buffer.", "take_profit_logic": "Exactly two times actual entry risk with at least 30 pips reward.", "time_exit_logic": "First M1 close at or after 16:00 London and never after 300 minutes.", "maximum_trades_per_day": 1, "direction_rules": ["Buy after positive impulse and retained reclaim.", "Sell mirrors the same rule."], "spread_cost_gate": "Only frozen normal-session base/stress cost models; no execution inference.", "expected_minimum_holding_minutes": 60, "expected_maximum_holding_minutes": 240, "hard_maximum_holding_minutes": 300, "allow_overnight_positions": False, "forbidden_conditions": ["Missing/nonconsecutive required M1", "weekend/time mismatch", "external data", "future data", "position management variation", "multiple or overnight positions"]}
    payload["strategies"].append({"research_id": "strategy_17_london_new_york_intraday_continuation_v1", "strategy_name": STRATEGY_NAME, "implementation": None, "hypothesis": "A sufficiently large and efficient four-hour London impulse that survives a shallow one-hour pullback may continue into the New York overlap.", "economic_rationale": "Holding for hours and requiring a 30-pip minimum reward targets movements large enough that normal-session broker friction is not the main economic determinant.", "date_proposed": "2026-08-30", "date_provenance": "Prospectively preregistered after explicit user authorization of the lower-turnover intraday pivot, before implementation or development-data access.", "frozen_rules": rules, "frozen_parameters": params, "frozen_specification": specification, "permitted_development_dataset_id": "dukascopy_eurusd_m1_development_2019_2023", "required_broker_cost_model_id": "roboforex_ecn_eurusd_intraday_base_v1", "promotion_gate_id": "strategy_17_intraday_economic_gate_v1", "experiments_performed": [], "status": "PROPOSED", "decision": "UNDECIDED", "decision_reason": "Prospectively frozen; implementation and development evaluation have not started."})
    payload["updated_at"] = datetime.now(UTC).isoformat()
    validated = ResearchRegistry.model_validate(payload)
    temporary = REGISTRY_PATH.with_name(f".{REGISTRY_PATH.name}.strategy17.tmp")
    temporary.write_text(json.dumps(validated.model_dump(mode="json"), indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(REGISTRY_PATH)
    print(f"registered {STRATEGY_NAME}")


if __name__ == "__main__":
    main()
