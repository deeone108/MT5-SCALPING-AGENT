"""Record Strategy 18's immutable primary-gate rejection in the cross-pair registry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.research.cross_pair_registry import CrossPairResearchRegistry

REGISTRY = Path("config/cross_pair_research_registry.json")
REPORT = Path("reports/strategy18/strategy18_early_stop_rejection.json")
RESEARCH_ID = "strategy_18_london_asian_range_failed_auction_v1"
IMPLEMENTATION = "src/mt5_scalping_agent/backtesting/london_asian_range_failed_auction.py"


def main() -> None:
    evidence = json.loads(REPORT.read_text(encoding="utf-8"))
    if evidence.get("research_id") != RESEARCH_ID or evidence.get("decision") != "REJECTED_PRIMARY_GATES":
        raise ValueError("Strategy 18 rejection evidence is missing or incompatible")
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for proposal in payload["proposals"]:
        if proposal["research_id"] != RESEARCH_ID:
            continue
        if proposal["status"] == "REJECTED":
            print("Strategy 18 rejection already recorded")
            return
        if proposal["status"] != "PROPOSED" or proposal.get("implementation") is not None or proposal.get("experiments_performed"):
            raise ValueError("Strategy 18 proposal is not eligible for first rejection record")
        now = datetime.now(UTC).isoformat()
        proposal["status"] = "REJECTED"
        proposal["implementation"] = IMPLEMENTATION
        proposal["experiments_performed"] = [{"experiment_id": "strategy18_eurusd_base_2019_primary_gate", "report_path": REPORT.as_posix(), "recorded_at": now, "decision": "REJECTED_PRIMARY_GATES"}]
        payload["updated_at"] = now
        validated = CrossPairResearchRegistry.model_validate(payload)
        temporary = REGISTRY.with_name(f".{REGISTRY.name}.strategy18-rejection.tmp")
        temporary.write_text(json.dumps(validated.model_dump(mode="json"), indent=2), encoding="utf-8")
        temporary.replace(REGISTRY)
        print("recorded Strategy 18 rejection")
        return
    raise ValueError("Strategy 18 registry entry is missing")


if __name__ == "__main__":
    main()