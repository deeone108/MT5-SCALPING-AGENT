"""One-time prospective Strategy 16 registry migration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.research.registry import ResearchRegistry


REGISTRY_PATH = Path("config/research_registry.json")
STRATEGY_NAME = "scheduled_us_macro_shock_continuation"


def main() -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if any(item["strategy_name"] == STRATEGY_NAME for item in payload["strategies"]):
        raise SystemExit("Strategy 16 is already registered; refusing to rewrite frozen inputs")

    payload["broker_cost_models"].extend(
        [
            {
                "cost_model_id": "roboforex_ecn_eurusd_news_base_v1",
                "broker": "RoboForex Ltd",
                "account_type": "RoboForex-ECN demo news-window research base",
                "symbol": "EURUSD",
                "point_size": 0.00001,
                "spread_points": 4.0,
                "slippage_points": 2.0,
                "commission_per_lot_per_side": 2.0,
                "currency": "USD",
                "calibration_evidence": "Conservative predeclared Strategy 16 news-window base: prior captured New York maximum spread of 4 points, 2-point slippage assumption, and published USD 2 per standard lot per side commission. No claim of event-tick calibration.",
            },
            {
                "cost_model_id": "roboforex_ecn_eurusd_news_stress_v1",
                "broker": "RoboForex Ltd",
                "account_type": "RoboForex-ECN demo news-window research stress",
                "symbol": "EURUSD",
                "point_size": 0.00001,
                "spread_points": 10.0,
                "slippage_points": 5.0,
                "commission_per_lot_per_side": 2.0,
                "currency": "USD",
                "calibration_evidence": "Predeclared Strategy 16 news stress chosen before results to model quote withdrawal and adverse entry around 08:30 New York. It is intentionally harsher than captured normal-session costs but is not historical event-tick execution evidence.",
            },
        ]
    )

    payload["promotion_gates"].append(
        {
            "gate_schema_version": 2,
            "gate_id": "strategy_16_event_economic_gate_v1",
            "declared_on": "2026-08-30",
            "provenance_note": "Prospectively frozen in docs/STRATEGY_16_RESEARCH_BRIEF.md before implementation and before any Strategy 16 development-result access; thresholds must not be weakened after results.",
            "base_cost_model_id": "roboforex_ecn_eurusd_news_base_v1",
            "stress_cost_model_id": "roboforex_ecn_eurusd_news_stress_v1",
            "minimum_gross_expectancy_pips": 3.0,
            "minimum_gross_block_bootstrap_lower_bound_pips": 1.5,
            "minimum_base_net_expectancy_pips": 2.0,
            "minimum_stress_net_expectancy_pips": 1.0,
            "minimum_median_mfe_pips": 8.0,
            "mfe_exceedance_threshold_pips": 6.0,
            "minimum_mfe_exceedance_ratio": 0.60,
            "minimum_median_mfe_mae_ratio": 1.5,
            "maximum_base_cost_mfe_ratio": 0.15,
            "maximum_stress_cost_mfe_ratio": 0.25,
            "minimum_annual_signals": 40,
            "maximum_annual_signals": 180,
            "maximum_entries_per_day": 1,
            "minimum_median_holding_minutes": 10,
            "maximum_median_holding_minutes": 60,
            "hard_maximum_holding_minutes": 80,
            "allow_overnight_positions": False,
            "minimum_stop_pips": 5.0,
            "minimum_stop_stress_cost_multiple": 2.5,
            "minimum_reward_stress_cost_multiple": 4.0,
            "minimum_cost_adjusted_reward_risk": 1.25,
            "bootstrap_confidence_level": 0.95,
            "bootstrap_units": ["day", "week"],
            "minimum_effective_sample_formula": "ceil(((1.96 + 0.84) * sample_standard_deviation_of_stress_net_pips / 1.0)^2)",
            "require_block_bootstrap_pass": True,
            "require_effective_sample_size_pass": True,
            "require_downside_tail_diagnostic": True,
            "minimum_base_profit_factor": 1.35,
            "minimum_stress_profit_factor": 1.15,
            "minimum_positive_years": 4,
            "development_year_count": 5,
            "minimum_positive_active_month_ratio": 0.55,
            "maximum_drawdown_percent": 10.0,
            "maximum_strongest_year_profit_contribution": 0.40,
            "maximum_top_decile_trade_profit_contribution": 0.50,
            "require_unit_exposure_pass": True,
            "require_risk_sized_portfolio_pass": True,
            "require_predefined_cost_stress_pass": True,
            "require_parameter_neighborhood_pass": True,
            "parameter_neighborhood_policy": "Only after every primary fixed-candidate gate passes, run ten one-factor cases without selection: shock displacement 6/8 pips; shock/baseline range multiple 1.75/2.25; retained displacement 0.60/0.80; maximum stabilization retracement 0.30/0.50; target reward/risk 2.00/2.50. Every case must have positive stress expectancy; at least 8/10 must retain gross expectancy >=3.0 pips and stress net expectancy >=1.0 pip; median neighbor base/stress PF must be >=1.35/1.15. Never replace the frozen candidate with a neighbor.",
            "require_tick_replay_pass": True,
        }
    )

    frozen_rules = [
        "Use validated UTC EURUSD bid M1 OHLCV and America/New_York zoneinfo civil time; Monday-Friday only.",
        "Require every exact M1 bar from 07:30 through 08:39 New York time. Form twelve non-overlapping completed M5 baseline bars over 07:30-08:29, the 08:30-08:34 shock, and the 08:35-08:39 stabilization.",
        "Let P0 be 08:29 close, D be 08:34 close minus P0, A=abs(D), and R be aggregate 08:30-08:34 high-low. Require A>=7 pips, R>=max(2 times baseline median M5 range, baseline linear Q90), A/R>=0.70, and directional adverse excursion<=0.20R.",
        "BUY uses D>0 and SELL D<0. During stabilization no close may cross the 50% retained-displacement level; maximum retracement from the shock close is 40% of A.",
        "The 08:39 close must retain at least 70% of A and reaccelerate at least 0.5 pip beyond the 08:37 close in the shock direction.",
        "Emit at most one intent per New York date at 08:39 and enter only on the exact 08:40 M1 open. A rejected emitted intent consumes the date.",
        "BUY stop is min(stabilization low, P0+0.50A)-0.5 pip; SELL mirrors with max(stabilization high, P0-0.50A)+0.5 pip. At actual entry require 5-15 pips risk.",
        "Target is exactly 2.25 times actual planned risk from entry and remaining reward must be at least 8 pips. Under 1.9-pip stress reference require (reward-1.9)/(risk+1.9)>=1.25, spread<=10 points, and all-in reference cost<=1.9 pips.",
        "Exit a single full position at stop or target, else the first M1 close at or after 10:00 New York, never later than 80 elapsed minutes; stop precedes target and target precedes time exit on a shared candle.",
        "No external release calendar, survey expectation, realized announcement, volume/order flow, future candle, pyramiding, averaging, partial exit, trailing stop, break-even move, concurrent position, or overnight position is permitted. Fail on an open-position M1 gap over 60 seconds.",
    ]
    frozen_parameters = {
        "pip_size": 0.0001,
        "timezone": "America/New_York",
        "eligible_weekdays": [0, 1, 2, 3, 4],
        "required_start_local": "07:30",
        "baseline_end_local": "08:29",
        "shock_start_local": "08:30",
        "shock_end_local": "08:34",
        "stabilization_start_local": "08:35",
        "signal_time_local": "08:39",
        "entry_time_local": "08:40",
        "hard_exit_time_local": "10:00",
        "baseline_m5_bars": 12,
        "shock_minutes": 5,
        "stabilization_minutes": 5,
        "minimum_shock_displacement_pips": 7.0,
        "minimum_shock_baseline_range_multiple": 2.0,
        "baseline_range_quantile": 0.90,
        "quantile_interpolation": "linear",
        "minimum_directional_efficiency": 0.70,
        "maximum_adverse_excursion_fraction": 0.20,
        "minimum_intrastabilization_retained_fraction": 0.50,
        "maximum_stabilization_retracement_fraction": 0.40,
        "minimum_final_retained_fraction": 0.70,
        "reacceleration_reference_minute_local": "08:37",
        "minimum_reacceleration_pips": 0.5,
        "stop_buffer_pips": 0.5,
        "minimum_stop_pips": 5.0,
        "maximum_stop_pips": 15.0,
        "target_reward_risk_multiple": 2.25,
        "minimum_reward_pips": 8.0,
        "stress_reference_cost_pips": 1.9,
        "minimum_cost_adjusted_reward_risk": 1.25,
        "maximum_spread_points": 10.0,
        "maximum_all_in_cost_pips": 1.9,
        "maximum_emitted_signals_per_ny_day": 1,
        "maximum_holding_minutes": 80,
        "entry_delay_bars_m1": 1,
        "require_exact_next_m1": True,
        "parameter_neighborhoods": [
            {"parameter": "minimum_shock_displacement_pips", "values": [6.0, 8.0]},
            {"parameter": "minimum_shock_baseline_range_multiple", "values": [1.75, 2.25]},
            {"parameter": "minimum_final_retained_fraction", "values": [0.60, 0.80]},
            {"parameter": "maximum_stabilization_retracement_fraction", "values": [0.30, 0.50]},
            {"parameter": "target_reward_risk_multiple", "values": [2.00, 2.50]},
        ],
        "unit_exposure_model": {"sizing_mode": "research_fixed_lot", "fixed_volume_lots": 1.0, "initial_equity_usd": 10000.0},
        "risk_sized_portfolio_model": {"sizing_mode": "risk_percent", "initial_equity_usd": 10000.0, "risk_percent_per_trade": 0.25, "max_lot_size": 1.0, "max_exposure_lots": 1.0, "max_symbol_exposure_lots": 1.0, "max_open_positions": 1, "min_reward_risk_ratio": 1.25, "max_spread_points": 10.0, "max_market_data_age_seconds": 60.0, "portfolio_circuit_breakers": "nonbinding during diagnostic", "maximum_daily_entries": 1},
        "robustness_settings": {"random_seed": 20260830, "bootstrap_samples": 10000, "confidence_level": 0.95, "bootstrap_units": ["UTC calendar day", "ISO UTC calendar week"], "interval_method": "percentile with linear quantiles", "promotion_order": "primary base/stress unit economics first; conditional robustness only after complete primary pass"},
        "open_position_data_gap_policy": "Fail loudly when consecutive M1 candles during an open position are more than 60 seconds apart.",
    }
    payload["strategies"].append(
        {
            "research_id": "strategy_16_scheduled_us_macro_shock_continuation_v1",
            "strategy_name": STRATEGY_NAME,
            "implementation": None,
            "hypothesis": "An unusually large and directionally efficient EURUSD displacement during the fixed 08:30 America/New_York U.S. macro-release window that retains most of its move during a five-minute stabilization period can continue after 08:40 because interpretation and risk transfer may remain incomplete after the first illiquid burst.",
            "economic_rationale": "Scheduled public information arrival repeatedly concentrates volatility and price discovery at 08:30 New York. Waiting through the first ten minutes avoids the initial jump and seeks a larger residual move at no more than one trade per day, with structural 5-15 pip risk and 2.25R reward under conservative 1.0/1.9-pip research costs.",
            "date_proposed": "2026-08-30",
            "date_provenance": "Prospectively preregistered after explicit user authorization and before implementation or any Strategy 16 development-data access.",
            "frozen_rules": frozen_rules,
            "frozen_parameters": frozen_parameters,
            "frozen_specification": {
                "specification_schema_version": 1,
                "market_behavior": "Scheduled-news-clock abnormal EURUSD displacement followed by short stabilization, retention, and delayed same-direction price discovery.",
                "persistence_rationale": "Recurring scheduled public information, heterogeneous interpretation, staged risk transfer, and temporarily impaired liquidity can repeatedly delay complete price discovery beyond the first five-minute jump.",
                "timeframe_hierarchy": ["UTC M1 bid OHLCV execution", "Twelve completed non-overlapping M5 baseline bars", "America/New_York event clock and five-minute shock/stabilization composites"],
                "session_restrictions": ["Monday-Friday America/New_York dates", "Exact 07:30-08:40 local sequence", "Signal only at 08:39 and entry only at 08:40", "Hard exit at or before 10:00 local"],
                "features_and_indicators": ["Baseline M5 raw-range median and linear Q90", "Five-minute shock displacement/range/efficiency", "Directional adverse excursion", "Stabilization retained displacement and retracement", "08:37-to-08:39 reacceleration", "Structural stabilization stop and fixed 2.25R target"],
                "lookback_periods": {"baseline_m5": 12, "shock_m1": 5, "stabilization_m1": 5, "total_required_pre_signal_m1": 70},
                "entry_logic": ["At 08:39 recognize only a shock satisfying every frozen abnormality and efficiency threshold.", "Require all stabilization retention, retracement, and reacceleration conditions.", "Emit one intent for the date and enter only on exact next-minute 08:40 open after actual-entry economics revalidation."],
                "exit_logic": ["Single full-position stop or target.", "Otherwise exit at first M1 close at or after 10:00 New York and no later than 80 elapsed minutes.", "Conservative shared-candle order: stop, target, time exit."],
                "stop_loss_logic": "BUY uses min stabilization low and 50%-retention level minus 0.5 pip; SELL mirrors. Actual risk must remain 5-15 pips.",
                "take_profit_logic": "Exactly 2.25 times actual planned risk from entry, at least 8 pips, and passing the frozen stress-cost-adjusted reward/risk gate.",
                "time_exit_logic": "First M1 close at or after 10:00 America/New_York, never more than 80 elapsed minutes after exact 08:40 entry.",
                "maximum_trades_per_day": 1,
                "direction_rules": ["BUY only after positive qualifying shock and retained/reaccelerating stabilization.", "SELL is the exact mirror.", "No opposite or second signal on the same New York date."],
                "spread_cost_gate": "Use 1.9-pip stress reference; spread<=10 points; risk 5-15 pips; reward>=8 pips; (reward-1.9)/(risk+1.9)>=1.25.",
                "expected_minimum_holding_minutes": 10,
                "expected_maximum_holding_minutes": 60,
                "hard_maximum_holding_minutes": 80,
                "allow_overnight_positions": False,
                "forbidden_conditions": ["Missing, duplicate, off-grid, nonfinite, or nonconsecutive required M1 bar", "Weekend or any local time/date mismatch", "Failed shock size/range/efficiency/adverse-excursion condition", "Failed stabilization retention/retracement/reacceleration condition", "Non-exact 08:40 entry or second emitted daily intent", "Stop/reward/cost-adjusted-RR/spread/all-in-cost failure", "External news calendar, release value, market expectation, order flow, volume, future bar, or discretionary classification", "Pyramiding, averaging, partial exit, trailing stop, break-even move, concurrent or overnight position"],
            },
            "permitted_development_dataset_id": "dukascopy_eurusd_m1_development_2019_2023",
            "required_broker_cost_model_id": "roboforex_ecn_eurusd_news_base_v1",
            "promotion_gate_id": "strategy_16_event_economic_gate_v1",
            "experiments_performed": [],
            "status": "PROPOSED",
            "decision": "UNDECIDED",
            "decision_reason": "Prospectively frozen; implementation and development evaluation have not started.",
        }
    )
    payload["updated_at"] = datetime.now(UTC).isoformat()
    validated = ResearchRegistry.model_validate(payload)
    temporary = REGISTRY_PATH.with_name(f".{REGISTRY_PATH.name}.strategy16.tmp")
    temporary.write_text(json.dumps(validated.model_dump(mode="json"), indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(REGISTRY_PATH)
    print(f"registered {STRATEGY_NAME}")


if __name__ == "__main__":
    main()