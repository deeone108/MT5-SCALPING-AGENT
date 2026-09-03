"""One-time, user-authorized correction of unused Strategy 17 metadata."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.research.registry import ResearchRegistry


PATH = Path("config/research_registry.json")
NAME = "london_new_york_intraday_continuation"


def main() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    record = next(item for item in payload["strategies"] if item["strategy_name"] == NAME)
    if record["status"] != "PROPOSED" or record["decision"] != "UNDECIDED" or record["experiments_performed"]:
        raise SystemExit("Strategy 17 correction is allowed only before implementation or evidence")
    record["frozen_parameters"].update({
        "pip_size": 0.0001,
        "stress_reference_cost_pips": 0.9,
        "minimum_cost_adjusted_reward_risk": 1.5,
        "maximum_spread_points": 3.0,
        "maximum_all_in_cost_pips": 0.9,
    })
    record["date_provenance"] = (
        "Initially registered before development-data access. Corrected on 2026-08-31 "
        "with explicit user authorization to add omitted runtime cost/economic defaults; "
        "no implementation, archive load, result, or completed experiment existed."
    )
    record["decision_reason"] = (
        "Prospectively frozen after user-authorized pre-evaluation metadata correction; "
        "implementation and development evaluation have not started."
    )
    payload["updated_at"] = datetime.now(UTC).isoformat()
    validated = ResearchRegistry.model_validate(payload)
    temporary = PATH.with_name(f".{PATH.name}.strategy17-correction.tmp")
    temporary.write_text(json.dumps(validated.model_dump(mode="json"), indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(PATH)
    print("corrected unused Strategy 17 preregistration")


if __name__ == "__main__":
    main()
