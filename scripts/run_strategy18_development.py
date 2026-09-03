"""Run the preregistered Strategy 18 on isolated four-pair development data only."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from math import fsum
from pathlib import Path
from statistics import median
from typing import Any

from mt5_scalping_agent.backtesting import BacktestConfig, BacktestResult, CandleBacktester, PositionSizingMode
from mt5_scalping_agent.backtesting.london_asian_range_failed_auction import (
    LondonAsianRangeFailedAuctionConfig,
    LondonAsianRangeFailedAuctionStrategy,
)
from mt5_scalping_agent.backtesting.reporting import backtest_summary
from mt5_scalping_agent.research.cross_pair import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    CrossPairDevelopmentSpec,
    evaluate_pair_development,
    load_frozen_cost_model,
)
from mt5_scalping_agent.research.cross_pair_registry import load_cross_pair_registry
from mt5_scalping_agent.research.manifest import write_json_atomic
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


RESEARCH_ID = "strategy_18_london_asian_range_failed_auction_v1"
STRATEGY_NAME = "london_asian_range_failed_auction"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
INITIAL_BALANCE = 10_000.0
FIXED_VOLUME_LOTS = 1.0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Strategy 18 only on four-pair 2019-2023 development data."
    )
    parser.add_argument("--archive-root", type=Path, default=Path("data"))
    parser.add_argument("--cost-models", type=Path, default=Path("config/cross_pair_cost_models.json"))
    parser.add_argument("--contract-audit", type=Path, default=Path("reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json"))
    parser.add_argument("--registry", type=Path, default=Path("config/cross_pair_research_registry.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/strategy18/strategy18_four_pair_development.json"))
    parser.add_argument("--checkpoint", type=Path, default=Path("reports/strategy18/strategy18_four_pair_development.checkpoint.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    _validate_preregistration(args.registry)
    symbols = _load_contracts(args.contract_audit)
    pair_reports: dict[str, object] = {}
    for pair in PAIRS:
        spec = CrossPairDevelopmentSpec(pair, symbols[pair])
        scenarios: dict[str, object] = {}
        for scenario in ("base", "stress"):
            model = load_frozen_cost_model(args.cost_models, spec, scenario)
            stress = load_frozen_cost_model(args.cost_models, spec, "stress")
            results: list[BacktestResult] = []
            diagnostics: dict[str, int] = {}
            for year in range(DEVELOPMENT_START.year, DEVELOPMENT_END.year):
                strategy = LondonAsianRangeFailedAuctionStrategy(
                    spread_points=model.spread_points,
                    config=LondonAsianRangeFailedAuctionConfig(
                        pip_size=spec.pip_size,
                        stress_cost_pips=stress.round_trip_cost_pips(spec),
                        maximum_spread_points=stress.spread_points,
                    ),
                )
                result = _simulate_year(
                    spec, model, strategy, args.archive_root, year, stress.spread_points
                )
                results.append(result)
                diagnostics = _merge_diagnostics(diagnostics, strategy.diagnostics)
                _write_checkpoint(args.checkpoint, pair, scenario, year, result.trade_count)
                print(f"Completed {pair} {scenario} {year}: {result.trade_count} trades", flush=True)
            combined = _merge_results(results)
            scenarios[scenario] = _scenario_report(combined, spec, diagnostics)
        pair_reports[pair] = {
            "symbol_contract": symbols[pair].model_dump(mode="json"),
            "pip_size": spec.pip_size,
            "base": scenarios["base"],
            "stress": scenarios["stress"],
            "primary_gates": _primary_gates(scenarios["base"], scenarios["stress"]),
        }

    aggregate = _aggregate(pair_reports)
    report = {
        "purpose": "Strategy 18 preregistered four-pair development evaluation; research only, no execution",
        "research_id": RESEARCH_ID,
        "strategy_name": STRATEGY_NAME,
        "period": {
            "start": DEVELOPMENT_START.isoformat(),
            "end_exclusive": DEVELOPMENT_END.isoformat(),
            "post_selection_data_loaded": False,
        },
        "pairs": list(PAIRS),
        "fixed_research_volume_lots": FIXED_VOLUME_LOTS,
        "primary_gate_policy": {
            "annual_trades": [50, 220],
            "minimum_gross_expectancy_pips": 3.0,
            "minimum_base_net_expectancy_pips": 1.5,
            "minimum_stress_net_expectancy_pips": 0.75,
            "minimum_base_profit_factor": 1.30,
            "minimum_stress_profit_factor": 1.15,
            "minimum_positive_years": 4,
            "minimum_positive_active_month_ratio": 0.55,
            "minimum_median_mfe_pips": 8.0,
            "minimum_median_mfe_mae_ratio": 1.5,
            "aggregate_stress_profitable_and_no_negative_pair": True,
        },
        "pair_results": pair_reports,
        "aggregate": aggregate,
        "decision": "PASS_PRIMARY_GATES" if aggregate["all_primary_gates_passed"] else "REJECTED_PRIMARY_GATES",
        "next_action": (
            "Run robustness diagnostics only if every primary gate passes."
            if aggregate["all_primary_gates_passed"]
            else "Stop: do not tune, select a pair, load 2024-2026 data, or implement execution."
        ),
    }
    write_json_atomic(args.report, report)
    print(f"Report: {args.report}", flush=True)
    return 0


def _simulate_year(
    spec: CrossPairDevelopmentSpec,
    model: object,
    strategy: LondonAsianRangeFailedAuctionStrategy,
    archive_root: Path,
    year: int,
    maximum_spread_points: float,
) -> BacktestResult:
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    if not (DEVELOPMENT_START <= start < end <= DEVELOPMENT_END):
        raise ValueError("Strategy 18 annual run must remain within frozen development")
    candles = LocalResearchArchive(archive_root).load_m1(spec.normalized_symbol, start, end)
    config = BacktestConfig(
        initial_balance=INITIAL_BALANCE,
        spread_points=model.spread_points,
        slippage_points=model.slippage_points,
        commission_per_lot_per_side=model.commission_per_lot_per_side_usd,
        position_sizing_mode=PositionSizingMode.RESEARCH_FIXED_LOT,
        fixed_volume_lots=FIXED_VOLUME_LOTS,
    )
    return CandleBacktester(config, RiskEngine(_research_limits(maximum_spread_points)), spec.broker_symbol).run(candles, strategy)


def _merge_diagnostics(current: dict[str, int], incoming: dict[str, int]) -> dict[str, int]:
    merged = dict(current)
    for key, value in incoming.items():
        merged[key] = merged.get(key, 0) + value
    return dict(sorted(merged.items()))


def _merge_results(results: list[BacktestResult]) -> BacktestResult:
    if not results:
        raise ValueError("Strategy 18 annual evaluation produced no results")
    trades = tuple(trade for result in results for trade in result.trades)
    rejected = tuple(reason for result in results for reason in result.rejected_intents)
    import pandas as pd
    curves = []
    realized = 0.0
    for result in results:
        curve = result.equity_curve.copy()
        if not curve.empty:
            curve["equity"] = curve["equity"] + realized
            curves.append(curve)
        realized += result.net_profit
    return BacktestResult(trades, rejected, pd.concat(curves, ignore_index=True), None)


def _write_checkpoint(path: Path, pair: str, scenario: str, year: int, trades: int) -> None:
    document = {
        "purpose": "Strategy 18 annual-progress checkpoint, not final research evidence",
        "research_id": RESEARCH_ID,
        "period": {"start": DEVELOPMENT_START.isoformat(), "end_exclusive": DEVELOPMENT_END.isoformat()},
        "latest_completed": {"pair": pair, "scenario": scenario, "year": year, "trade_count": trades},
        "post_selection_data_loaded": False,
    }
    write_json_atomic(path, document)

def _validate_preregistration(path: Path) -> None:
    registry = load_cross_pair_registry(path)
    proposals = {item.research_id: item for item in registry.proposals}
    proposal = proposals.get(RESEARCH_ID)
    if proposal is None or proposal.strategy_name != STRATEGY_NAME:
        raise ValueError("Strategy 18 preregistration is missing")
    if proposal.status != "PROPOSED" or proposal.implementation is not None or proposal.experiments_performed:
        raise ValueError("Strategy 18 preregistration is no longer a clean initial evaluation")
    if tuple(binding.symbol for binding in proposal.pair_bindings) != PAIRS:
        raise ValueError("Strategy 18 preregistration pairs changed")


def _load_contracts(path: Path) -> dict[str, SymbolRiskSpec]:
    document = json.loads(path.read_text(encoding="utf-8"))
    models = document.get("models")
    if not isinstance(models, dict):
        raise ValueError("contract audit has no models")
    symbols: dict[str, SymbolRiskSpec] = {}
    for pair in PAIRS:
        entry = models.get(pair)
        if not isinstance(entry, dict) or not isinstance(entry.get("symbol_contract"), dict):
            raise ValueError(f"contract audit missing {pair}")
        symbols[pair] = SymbolRiskSpec.model_validate(entry["symbol_contract"])
    return symbols


def _research_limits(maximum_spread_points: float) -> RiskLimits:
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
        min_reward_risk_ratio=1.5,
        max_spread_points=maximum_spread_points,
    )


def _scenario_report(
    result: BacktestResult,
    spec: CrossPairDevelopmentSpec,
    diagnostics: dict[str, int],
) -> dict[str, object]:
    gross = [_pips(trade.gross_pnl, trade.volume_lots, spec) for trade in result.trades]
    net = [_pips(trade.net_pnl, trade.volume_lots, spec) for trade in result.trades]
    mfe = [trade.mfe / spec.pip_size for trade in result.trades if trade.mfe is not None]
    mae = [abs(trade.mae) / spec.pip_size for trade in result.trades if trade.mae is not None]
    annual, months = _period_pips(result, spec)
    return {
        "summary": backtest_summary(result, symbol=spec.normalized_symbol),
        "trade_pips": {
            "gross_expectancy": _mean(gross),
            "net_expectancy": _mean(net),
            "median_mfe": float(median(mfe)) if mfe else None,
            "median_adverse_mae": float(median(mae)) if mae else None,
        },
        "annual": _period_document(annual),
        "active_months": _period_document(months),
        "strategy_diagnostics": diagnostics,
    }


def _pips(amount: float, lots: float, spec: CrossPairDevelopmentSpec) -> float:
    pip_value = spec.pip_size / spec.broker_symbol.tick_size * spec.broker_symbol.tick_value
    return amount / (lots * pip_value)


def _period_pips(result: BacktestResult, spec: CrossPairDevelopmentSpec) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    annual: dict[str, list[float]] = defaultdict(list)
    months: dict[str, list[float]] = defaultdict(list)
    for trade in result.trades:
        timestamp = trade.entry_time.astimezone(UTC)
        value = _pips(trade.net_pnl, trade.volume_lots, spec)
        annual[str(timestamp.year)].append(value)
        months[timestamp.strftime("%Y-%m")].append(value)
    return annual, months


def _period_document(values: dict[str, list[float]]) -> dict[str, object]:
    return {
        key: {"trade_count": len(rows), "net_pips": fsum(rows), "positive": fsum(rows) > 0}
        for key, rows in sorted(values.items())
    }


def _primary_gates(base: object, stress: object) -> list[dict[str, object]]:
    base_data, stress_data = _as_mapping(base), _as_mapping(stress)
    base_summary, stress_summary = _as_mapping(base_data["summary"]), _as_mapping(stress_data["summary"])
    base_pips, stress_pips = _as_mapping(base_data["trade_pips"]), _as_mapping(stress_data["trade_pips"])
    stress_years = _as_mapping(stress_data["annual"])
    stress_months = _as_mapping(stress_data["active_months"])
    annual_counts = [int(_as_mapping(item)["trade_count"]) for item in stress_years.values()]
    positive_years = sum(bool(_as_mapping(item)["positive"]) for item in stress_years.values())
    positive_months = sum(bool(_as_mapping(item)["positive"]) for item in stress_months.values())
    median_mfe, median_mae = stress_pips["median_mfe"], stress_pips["median_adverse_mae"]
    return [
        _gate("annual_trades", annual_counts, len(annual_counts) == 5 and all(50 <= value <= 220 for value in annual_counts)),
        _gate("gross_expectancy_pips", stress_pips["gross_expectancy"], _at_least(stress_pips["gross_expectancy"], 3.0)),
        _gate("base_net_expectancy_pips", base_pips["net_expectancy"], _at_least(base_pips["net_expectancy"], 1.5)),
        _gate("stress_net_expectancy_pips", stress_pips["net_expectancy"], _at_least(stress_pips["net_expectancy"], 0.75)),
        _gate("base_profit_factor", base_summary["profit_factor"], _at_least(base_summary["profit_factor"], 1.30)),
        _gate("stress_profit_factor", stress_summary["profit_factor"], _at_least(stress_summary["profit_factor"], 1.15)),
        _gate("positive_years", positive_years, positive_years >= 4),
        _gate("positive_active_month_ratio", _ratio(positive_months, len(stress_months)), _at_least(_ratio(positive_months, len(stress_months)), 0.55)),
        _gate("median_mfe_pips", median_mfe, _at_least(median_mfe, 8.0)),
        _gate("median_mfe_mae_ratio", _ratio(median_mfe, median_mae), _at_least(_ratio(median_mfe, median_mae), 1.5)),
    ]


def _aggregate(pair_reports: dict[str, object]) -> dict[str, object]:
    reports = {pair: _as_mapping(value) for pair, value in pair_reports.items()}
    stress_net_pips = {
        pair: _as_mapping(_as_mapping(report["stress"])["active_months"])
        for pair, report in reports.items()
    }
    pair_nets = {
        pair: fsum(float(_as_mapping(row)["net_pips"]) for row in months.values())
        for pair, months in stress_net_pips.items()
    }
    all_pair_gates = all(
        all(row["status"] == "PASS" for row in _as_mapping(report)["primary_gates"])
        for report in reports.values()
    )
    aggregate_stress = fsum(pair_nets.values())
    return {
        "stress_net_pips_by_pair": pair_nets,
        "stress_net_pips_all_pairs": aggregate_stress,
        "aggregate_stress_profitable": aggregate_stress > 0,
        "no_pair_stress_negative": all(value >= 0 for value in pair_nets.values()),
        "all_pair_primary_gates_passed": all_pair_gates,
        "all_primary_gates_passed": all_pair_gates and aggregate_stress > 0 and all(value >= 0 for value in pair_nets.values()),
    }


def _as_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("expected report mapping")
    return value


def _gate(gate_id: str, observed: object, passed: bool) -> dict[str, object]:
    return {"gate_id": gate_id, "observed": observed, "status": "PASS" if passed else "FAIL"}


def _at_least(value: object, minimum: float) -> bool:
    return value == "infinity" or isinstance(value, (int, float)) and not isinstance(value, bool) and value >= minimum


def _ratio(numerator: object, denominator: object) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    return numerator / denominator if denominator > 0 else None


def _mean(values: list[float]) -> float | None:
    return fsum(values) / len(values) if values else None


if __name__ == "__main__":
    raise SystemExit(main())