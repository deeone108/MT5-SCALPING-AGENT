from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def materialize_registry_evidence(root: Path, payload: dict[str, Any]) -> None:
    """Create minimal synthetic reports from registry-owned expected values."""
    costs = {item["cost_model_id"]: item for item in payload["broker_cost_models"]}
    reports: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for strategy in payload["strategies"]:
        for evidence in strategy["experiments_performed"]:
            reports[evidence["report_path"]].append((strategy["strategy_name"], evidence))
    for relative, records in reports.items():
        cost_ids = {evidence["cost_model_id"] for _, evidence in records}
        assert len(cost_ids) == 1
        model = costs[cost_ids.pop()]
        report: dict[str, Any] = {"backtest_assumptions": {
            "spread_points": model["spread_points"],
            "slippage_points": model["slippage_points"],
            "commission_per_lot_per_side": model["commission_per_lot_per_side"],
        }}
        if records[0][1].get("continuous_summary") is not None:
            run_ids = {evidence["report_run_id"] for _, evidence in records}
            assert len(run_ids) == 1
            report["run_manifest"] = {"run_id": run_ids.pop()}
            report["results"] = [_continuous_result(name, evidence["continuous_summary"])
                                 for name, evidence in records]
        else:
            report["aggregates"] = [{"strategy": name, **aggregate}
                                    for name, evidence in records
                                    for aggregate in evidence["aggregates"]]
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _continuous_result(strategy: str, summary: dict[str, Any]) -> dict[str, Any]:
    fields = ("trade_count", "total_lots", "gross_pnl", "total_transaction_cost",
              "net_profit", "gross_expectancy_per_trade", "net_expectancy_per_trade",
              "profit_factor", "max_drawdown")
    return {
        "strategy": strategy,
        "period": {"name": "development", "start": summary["period_start"],
                   "end": summary["period_end_exclusive"], "end_exclusive": True,
                   "post_selection_data_used": False},
        "summaries": {
            "complete": {field: summary[field] for field in fields},
            "by_year": _period_rows(summary["year_count"], summary["positive_years"]),
            "by_month": _period_rows(summary["month_count"], summary["positive_months"]),
        },
    }


def _period_rows(count: int, positive: int) -> list[dict[str, float]]:
    return [{"net_profit": 1.0 if index < positive else -1.0} for index in range(count)]
