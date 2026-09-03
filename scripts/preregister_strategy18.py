"""One-time prospective registration of the four-pair Strategy 18 proposal."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.research.cross_pair_registry import CrossPairResearchRegistry


PATH = Path("config/cross_pair_research_registry.json")
NAME = "london_asian_range_failed_auction"


def main() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    if any(item["strategy_name"] == NAME for item in payload["proposals"]):
        raise SystemExit("Strategy 18 is already preregistered")
    rules = (
        "Use only completed UTC M1 bid OHLCV and Europe/London civil time.",
        "Require every M1 bar from 00:00-05:59 London for the Asian range.",
        "Between 07:00-09:00 London, require the first M5 close at least 8 pips outside that range.",
        "Within the next three completed M5 bars require a close at least 1 pip inside the range, then enter opposite the sweep at the next M1 open.",
        "Use sweep extreme plus one pip as stop; risk 8-25 pips; fixed 2R target with at least 16 pips reward.",
        "One emitted intent per London date; stop, target, or 12:00 London hard exit; never overnight.",
        "Use each pair's frozen stress cost gate and no external data, future data, indicators, or position management variations.",
    )
    payload["proposals"].append({
        "research_id": "strategy_18_london_asian_range_failed_auction_v1",
        "strategy_name": NAME,
        "proposed_at": datetime.now(UTC).isoformat(),
        "hypothesis": "A failed London excursion outside the completed Asian range can revert toward the range after a confirmed re-entry, producing an infrequent structural intraday opportunity.",
        "economic_rationale": "A one-trade-per-day range-failure design requires a 16-pip minimum planned reward and 2R target so frozen normal-session friction remains materially smaller than the planned move.",
        "frozen_rules": rules,
        "frozen_parameters": {
            "timezone": "Europe/London", "asian_start": "00:00", "asian_end": "05:59", "sweep_start": "07:00", "sweep_end": "09:00", "sweep_m5_close_pips": 8.0, "reentry_inside_pips": 1.0, "confirmation_m5_bars": 3, "stop_buffer_pips": 1.0, "minimum_stop_pips": 8.0, "maximum_stop_pips": 25.0, "target_reward_risk": 2.0, "minimum_reward_pips": 16.0, "hard_exit": "12:00", "maximum_holding_minutes": 240, "maximum_entries_per_london_day": 1,
            "primary_gates_per_pair": {"annual_trades": [50, 220], "minimum_gross_expectancy_pips": 3.0, "minimum_base_net_expectancy_pips": 1.5, "minimum_stress_net_expectancy_pips": 0.75, "minimum_base_pf": 1.30, "minimum_stress_pf": 1.15, "minimum_positive_years": 4, "minimum_positive_month_ratio": 0.55, "minimum_median_mfe_pips": 8.0, "minimum_median_mfe_mae_ratio": 1.5},
            "aggregate_gate": "stress-cost profitable across all four pairs and no individual pair negative",
        },
        "frozen_specification": {
            "specification_schema_version": 1, "market_behavior": "London failed auction beyond the completed Asian range followed by accepted re-entry.", "persistence_rationale": "London liquidity can test overnight range liquidity; a return inside the prior range may reflect failed price acceptance rather than a trend continuation.", "timeframe_hierarchy": ["UTC M1 execution", "completed M5 sweep and re-entry confirmation", "Europe/London session range"], "session_restrictions": ["Monday-Friday London dates", "Asian 00:00-05:59 range", "07:00-09:00 sweep", "12:00 hard exit"], "features_and_indicators": ["Asian high/low", "M5 sweep close", "M5 re-entry close", "sweep extreme structural stop"], "lookback_periods": {"asian_m1_minutes": 360, "confirmation_m5_bars": 3}, "entry_logic": ["First qualifying M5 sweep then confirmed inside-range M5 close.", "Enter only at the exact next M1 open opposite the sweep."], "exit_logic": ["Full stop, full target, or 12:00 London hard exit."], "stop_loss_logic": "Sweep extreme plus one pip buffer, constrained to 8-25 pips actual risk.", "take_profit_logic": "Exactly 2R and at least 16 pips, passing pair stress cost gate.", "time_exit_logic": "First M1 close at or after 12:00 London, no later than 240 minutes.", "maximum_trades_per_day": 1, "direction_rules": ["Sell after an upside sweep and confirmed inside-range close.", "Buy mirrors after a downside sweep."], "spread_cost_gate": "Pair-specific frozen stress spread and all-in cost; cost-adjusted reward/risk at least 1.50.", "expected_minimum_holding_minutes": 30, "expected_maximum_holding_minutes": 180, "hard_maximum_holding_minutes": 240, "allow_overnight_positions": False, "forbidden_conditions": ["Incomplete required bars", "future data", "external calendar or order flow", "Bollinger/RSI/ATR/MA filters", "pyramiding, averaging, trailing, partial exits, or concurrent positions"]
        },
        "pair_bindings": [
            {"symbol": pair, "development_archive_pattern": f"data/dukascopy_annual/{pair}_m1_{{2019..2023}}.csv.gz", "base_cost_scenario": "config/cross_pair_cost_models.json:base", "stress_cost_scenario": "config/cross_pair_cost_models.json:stress"}
            for pair in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
        ],
        "status": "PROPOSED"
    })
    payload["updated_at"] = datetime.now(UTC).isoformat()
    registry = CrossPairResearchRegistry.model_validate(payload)
    temporary = PATH.with_name(f".{PATH.name}.strategy18.tmp")
    temporary.write_text(json.dumps(registry.model_dump(mode="json"), indent=2), encoding="utf-8")
    temporary.replace(PATH)
    print(f"registered {NAME}")


if __name__ == "__main__":
    main()
