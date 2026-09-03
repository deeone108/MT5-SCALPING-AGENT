"""Deterministic diagnosis artifacts for completed continuous research reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from math import isclose, isfinite
from pathlib import Path
from typing import Any


ASSESSMENT_SCHEMA_VERSION = 1
DEVELOPMENT_START = "2019-01-01T00:00:00+00:00"
DEVELOPMENT_END = "2024-01-01T00:00:00+00:00"
MINIMUM_DIAGNOSTIC_TRADES = 300
MINIMUM_POSITIVE_YEAR_FRACTION = 0.60
MINIMUM_POSITIVE_MONTH_FRACTION = 0.50
MAX_STRONGEST_MONTH_CONTRIBUTION = 0.35
MAX_TOP_TEN_TRADE_CONTRIBUTION = 0.50
EXPECTED_YEARS = tuple(str(year) for year in range(2019, 2024))
EXPECTED_QUARTERS = tuple(
    f"{year}-Q{quarter}" for year in range(2019, 2024) for quarter in range(1, 5)
)
EXPECTED_MONTHS = tuple(
    f"{year}-{month:02d}" for year in range(2019, 2024) for month in range(1, 13)
)
EXPECTED_PARTITIONS = {
    "by_year": EXPECTED_YEARS,
    "by_quarter": EXPECTED_QUARTERS,
    "by_month": EXPECTED_MONTHS,
    "by_direction": ("BUY", "SELL"),
    "by_session": ("off_session", "london", "new_york", "london_new_york"),
    "by_volatility_regime": ("low", "normal", "high", "unavailable"),
}


class ContinuousAssessmentError(ValueError):
    """Raised when a source is not a complete, isolated continuous report."""


def load_completed_continuous_report(path: Path) -> dict[str, object]:
    """Load a final report while explicitly refusing checkpoint files."""
    if path.name.endswith(".checkpoint.json"):
        raise ContinuousAssessmentError("checkpoint files cannot be assessed as completed reports")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContinuousAssessmentError(f"could not read completed report {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContinuousAssessmentError("completed report root must be a JSON object")
    return value


def build_continuous_assessment(
    report: Mapping[str, object],
    *,
    source_label: str = "completed continuous report",
) -> tuple[dict[str, object], str]:
    """Validate a completed report and return machine and Markdown diagnoses."""
    validated = _validate_report(report)
    ranked_rows = sorted(
        validated["results"],
        key=lambda row: (-_number(row["summaries"]["complete"], "net_pnl"), str(row["strategy"])),
    )
    strategies = [_strategy_diagnosis(row) for row in ranked_rows]
    for rank, strategy in enumerate(strategies, start=1):
        strategy["rank_by_after_cost_net_pnl"] = rank

    caveats = _caveats(validated)
    diagnosis = {
        "gross_edge": {
            "required_point": 1,
            "strategies": [
                {
                    "strategy": row["strategy"],
                    "gross_pnl": row["economics"]["gross_pnl"],
                    "gross_expectancy_per_trade": row["economics"]["gross_expectancy_per_trade"],
                    "bootstrap_confidence_interval": row["uncertainty"]["gross_expectancy_per_trade"],
                }
                for row in strategies
            ],
        },
        "cost_decomposition": {
            "required_point": 2,
            "strategies": [
                {"strategy": row["strategy"], **row["costs"]} for row in strategies
            ],
        },
        "average_gross_edge_per_trade": {
            "required_point": 3,
            "strategies": [
                {
                    "strategy": row["strategy"],
                    "value": row["economics"]["gross_expectancy_per_trade"],
                }
                for row in strategies
            ],
        },
        "transaction_cost_per_trade": {
            "required_point": 4,
            "strategies": [
                {
                    "strategy": row["strategy"],
                    "value": row["costs"]["transaction_cost_per_trade"],
                    "spread": row["costs"]["spread_cost_per_trade"],
                    "slippage": row["costs"]["slippage_cost_per_trade"],
                    "commission": row["costs"]["commission_per_trade"],
                }
                for row in strategies
            ],
        },
        "break_even_cost_levels": {
            "required_point": 5,
            "strategies": [
                {"strategy": row["strategy"], **row["break_even"]}
                for row in strategies
            ],
        },
        "profit_concentration": {
            "required_point": 6,
            "strategies": [
                {"strategy": row["strategy"], **row["profit_concentration"]}
                for row in strategies
            ],
        },
        "temporal_stability": {
            "required_point": 7,
            "strategies": [
                {"strategy": row["strategy"], **row["temporal_stability"]}
                for row in strategies
            ],
        },
        "dominant_failure_mechanism": {
            "required_point": 8,
            "strategies": [
                {"strategy": row["strategy"], **row["failure_mechanism"]}
                for row in strategies
            ],
        },
    }
    machine = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "assessment_kind": "continuous_development_diagnosis",
        "source": {
            "label": source_label,
            "run_id": validated["run_manifest"]["run_id"],
            "symbol": validated["symbol"],
            "risk_profile": validated.get("risk_profile"),
        },
        "scope": {
            "development_start": DEVELOPMENT_START,
            "development_end_exclusive": DEVELOPMENT_END,
            "post_selection_data_used": False,
            "strategy_count": len(strategies),
            "ranking_basis": "after-cost net_pnl descending",
            "leading_strategy": strategies[0]["strategy"],
        },
        "decision_thresholds": {
            "minimum_diagnostic_trades": MINIMUM_DIAGNOSTIC_TRADES,
            "minimum_positive_active_year_fraction": MINIMUM_POSITIVE_YEAR_FRACTION,
            "minimum_positive_active_month_fraction": MINIMUM_POSITIVE_MONTH_FRACTION,
            "maximum_strongest_month_net_contribution": MAX_STRONGEST_MONTH_CONTRIBUTION,
            "maximum_top_ten_percent_trade_net_contribution": MAX_TOP_TEN_TRADE_CONTRIBUTION,
        },
        "required_diagnosis": diagnosis,
        "strategies": strategies,
        "caveats": caveats,
        "decision": {
            "deployment_approval": False,
            "new_strategy_proposed": False,
            "statement": "diagnostic evidence only; this assessment makes no strategy proposal or deployment approval",
        },
    }
    return machine, _markdown(machine)


def _validate_report(report: Mapping[str, object]) -> dict[str, Any]:
    if "checkpoint_schema_version" in report or (
        "manifest" in report and "run_manifest" not in report
    ):
        raise ContinuousAssessmentError("checkpoint payload cannot be assessed as a completed report")
    manifest = _mapping(report, "run_manifest")
    frozen = _mapping(manifest, "frozen")
    if frozen.get("run_kind") != "continuous_development_evaluation":
        raise ContinuousAssessmentError("report is not a continuous development evaluation")
    if frozen.get("timeframe") != "M1":
        raise ContinuousAssessmentError("continuous assessment requires the manifest-frozen M1 timeframe")
    _validate_periods(_mapping(report, "periods"), "report")
    _validate_periods(_mapping(frozen, "periods"), "manifest")

    results_value = report.get("results")
    if not isinstance(results_value, list) or not results_value:
        raise ContinuousAssessmentError("completed report must contain at least one result")
    expected_descriptors = frozen.get("strategies")
    if not isinstance(expected_descriptors, list) or not expected_descriptors:
        raise ContinuousAssessmentError("manifest does not contain frozen strategies")
    expected = {
        str(item.get("strategy_name"))
        for item in expected_descriptors
        if isinstance(item, dict) and item.get("strategy_name")
    }
    actual = [str(item.get("strategy")) for item in results_value if isinstance(item, dict)]
    if len(actual) != len(results_value) or len(set(actual)) != len(actual):
        raise ContinuousAssessmentError("completed report has missing or duplicate strategy results")
    if set(actual) != expected:
        raise ContinuousAssessmentError(
            "completed report result set does not match the manifest-frozen strategies"
        )

    validated_results: list[dict[str, Any]] = []
    for value in results_value:
        row = dict(value)
        strategy = str(row["strategy"])
        _validate_result_period(_mapping(row, "period"), strategy)
        _validate_diagnostic_methodology(row, strategy)
        _validate_result_accounting(row)
        validated_results.append(row)

    assumptions = _mapping(report, "backtest_assumptions")
    costs = _mapping(frozen, "transaction_costs")
    if not isclose(
        _number(assumptions, "spread_points"),
        _number(costs, "spread_points"),
        abs_tol=1e-12,
    ) or not isclose(
        _number(assumptions, "slippage_points"),
        _number(costs, "slippage_points"),
        abs_tol=1e-12,
    ):
        raise ContinuousAssessmentError("report cost assumptions differ from the manifest")
    commission_model = _mapping(costs, "commission_model")
    if not isclose(
        _number(assumptions, "commission_per_lot_per_side"),
        _number(commission_model, "amount"),
        abs_tol=1e-12,
    ):
        raise ContinuousAssessmentError("report commission differs from the manifest")
    runner_settings = _mapping(frozen, "runner_settings")
    if report.get("risk_profile") != runner_settings.get("risk_profile"):
        raise ContinuousAssessmentError("report risk profile differs from the manifest")

    return {
        **dict(report),
        "run_manifest": dict(manifest),
        "results": validated_results,
    }


def _validate_periods(periods: Mapping[str, object], label: str) -> None:
    development = _mapping(periods, "development")
    if (
        development.get("start") != DEVELOPMENT_START
        or development.get("end") != DEVELOPMENT_END
        or development.get("end_exclusive") is not True
    ):
        raise ContinuousAssessmentError(
            f"{label} is not isolated to [2019-01-01, 2024-01-01)"
        )
    post = _mapping(periods, "post_selection_robustness")
    if post.get("permitted_for_this_run") is not False:
        raise ContinuousAssessmentError(f"{label} permits post-selection data")


def _validate_result_period(period: Mapping[str, object], strategy: str) -> None:
    if (
        period.get("start") != DEVELOPMENT_START
        or period.get("end") != DEVELOPMENT_END
        or period.get("end_exclusive") is not True
        or period.get("post_selection_data_used") is not False
    ):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} result is not isolated to 2019-2023 development data"
        )


def _validate_diagnostic_methodology(
    row: Mapping[str, object], strategy: str
) -> None:
    if row.get("attribution_basis") != "trade_entry_time":
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} does not use trade-entry diagnostic attribution"
        )
    if row.get("session_definition") != (
        "DST-aware Europe/London and America/New_York local 08:00-13:00"
    ):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} does not declare the frozen DST-aware sessions"
        )
    volatility = _mapping(row, "volatility_regime_definition")
    if (
        volatility.get("signal_rule") is not False
        or volatility.get("observation_timing")
        != "only candles completed before trade entry"
    ):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} volatility regimes are not causal diagnostics"
        )

def _validate_result_accounting(row: Mapping[str, object]) -> None:
    strategy = str(row["strategy"])
    summaries = _mapping(row, "summaries")
    complete = _mapping(summaries, "complete")
    trade_count = _integer(complete, "trade_count")
    gross = _number(complete, "gross_pnl")
    spread = _number(complete, "total_spread_cost")
    slippage = _number(complete, "total_slippage_cost")
    commission = _number(complete, "total_commission")
    total_cost = _number(complete, "total_transaction_cost")
    net = _number(complete, "net_pnl")
    if any(value < 0 for value in (spread, slippage, commission, total_cost)):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} contains a negative transaction cost"
        )
    if not isclose(spread + slippage + commission, total_cost, rel_tol=1e-12, abs_tol=1e-8):
        raise ContinuousAssessmentError(f"strategy {strategy!r} cost decomposition is inconsistent")
    if not isclose(gross - total_cost, net, rel_tol=1e-12, abs_tol=1e-8):
        raise ContinuousAssessmentError(f"strategy {strategy!r} gross-cost-net identity failed")
    if not isclose(_number(complete, "net_profit"), net, rel_tol=1e-12, abs_tol=1e-8):
        raise ContinuousAssessmentError(f"strategy {strategy!r} legacy net field differs")
    rejection_reasons = complete.get("rejected_intent_reason_counts", {})
    if not isinstance(rejection_reasons, dict) or any(
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for count in rejection_reasons.values()
    ):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} rejection reason counts are invalid"
        )
    _validate_expectancy_fields(complete, strategy, trade_count, gross, net)
    _validate_summary_partitions(summaries, complete, strategy)

    statistics = _mapping(row, "statistical_robustness")
    sample = _mapping(statistics, "sample")
    if sample.get("accounting_identity_holds") is not True:
        raise ContinuousAssessmentError(f"strategy {strategy!r} statistical accounting audit failed")
    comparisons = (
        ("trade_count", float(trade_count)),
        ("gross_pnl", gross),
        ("total_transaction_cost", total_cost),
        ("net_pnl", net),
    )
    for field, expected in comparisons:
        actual = _number(sample, field)
        if not isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-8):
            raise ContinuousAssessmentError(
                f"strategy {strategy!r} statistical sample {field} differs from summary"
            )
    methodology = _mapping(statistics, "methodology")
    if methodology.get("serial_dependence_preserved") is not False or "IID" not in str(
        methodology.get("bootstrap_method", "")
    ):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} does not declare the expected IID bootstrap limitation"
        )
    consistency = _mapping(statistics, "consistency")
    _validate_statistical_calendar(
        _mapping(consistency, "yearly"), EXPECTED_YEARS, strategy, "yearly"
    )
    _validate_statistical_calendar(
        _mapping(consistency, "monthly"), EXPECTED_MONTHS, strategy, "monthly"
    )


def _validate_expectancy_fields(
    complete: Mapping[str, object],
    strategy: str,
    trade_count: int,
    gross: float,
    net: float,
) -> None:
    expected_gross = gross / trade_count if trade_count else None
    expected_net = net / trade_count if trade_count else None
    expected_break_even = (
        expected_gross
        if expected_gross is not None and expected_gross >= 0
        else None
    )
    comparisons = (
        ("gross_expectancy_per_trade", expected_gross),
        ("net_expectancy_per_trade", expected_net),
        ("break_even_transaction_cost_per_trade", expected_break_even),
    )
    for field, expected in comparisons:
        actual = _optional_number(complete.get(field))
        if expected is None:
            if complete.get(field) is not None:
                raise ContinuousAssessmentError(
                    f"strategy {strategy!r} {field} should be null"
                )
        elif actual is None or not isclose(
            actual, expected, rel_tol=1e-12, abs_tol=1e-8
        ):
            raise ContinuousAssessmentError(
                f"strategy {strategy!r} {field} does not reconcile to completed trades"
            )


def _validate_summary_partitions(
    summaries: Mapping[str, object],
    complete: Mapping[str, object],
    strategy: str,
) -> None:
    expected_totals = {
        "trade_count": float(_integer(complete, "trade_count")),
        "gross_pnl": _number(complete, "gross_pnl"),
        "total_spread_cost": _number(complete, "total_spread_cost"),
        "total_slippage_cost": _number(complete, "total_slippage_cost"),
        "total_commission": _number(complete, "total_commission"),
        "total_transaction_cost": _number(complete, "total_transaction_cost"),
        "net_pnl": _number(complete, "net_pnl"),
    }
    for partition, expected_labels in EXPECTED_PARTITIONS.items():
        rows = _sequence(summaries, partition)
        labels = tuple(
            str(row.get("group")) for row in rows if isinstance(row, dict)
        )
        if len(labels) != len(rows) or labels != expected_labels:
            raise ContinuousAssessmentError(
                f"strategy {strategy!r} {partition} labels are not the frozen "
                "development partition"
            )
        for field, expected in expected_totals.items():
            actual = sum(
                _number(row, field) for row in rows if isinstance(row, dict)
            )
            if not isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-8):
                raise ContinuousAssessmentError(
                    f"strategy {strategy!r} {partition} {field} does not "
                    "reconcile to complete"
                )


def _validate_statistical_calendar(
    calendar: Mapping[str, object],
    expected_labels: Sequence[str],
    strategy: str,
    label: str,
) -> None:
    rows = _sequence(calendar, "periods")
    labels = tuple(str(row.get("period")) for row in rows if isinstance(row, dict))
    if len(labels) != len(rows) or labels != tuple(expected_labels):
        raise ContinuousAssessmentError(
            f"strategy {strategy!r} statistical {label} labels leak outside 2019-2023"
        )

def _strategy_diagnosis(row: Mapping[str, Any]) -> dict[str, Any]:
    strategy = str(row["strategy"])
    summaries = _mapping(row, "summaries")
    complete = _mapping(summaries, "complete")
    statistics = _mapping(row, "statistical_robustness")
    bootstrap = _mapping(statistics, "bootstrap")
    consistency = _mapping(statistics, "consistency")
    concentration = _mapping(statistics, "concentration")
    trade_count = _integer(complete, "trade_count")
    total_lots = _number(complete, "total_lots")
    gross = _number(complete, "gross_pnl")
    spread = _number(complete, "total_spread_cost")
    slippage = _number(complete, "total_slippage_cost")
    commission = _number(complete, "total_commission")
    total_cost = _number(complete, "total_transaction_cost")
    net = _number(complete, "net_pnl")
    divisor = trade_count if trade_count else None
    cost_per_trade = total_cost / divisor if divisor else None
    commission_break_even_numerator = gross - spread - slippage
    commission_break_even = (
        commission_break_even_numerator / (2.0 * total_lots)
        if total_lots > 0 and commission_break_even_numerator >= 0
        else None
    )
    net_expectancy = _optional_number(complete.get("net_expectancy_per_trade"))
    gross_expectancy = _optional_number(complete.get("gross_expectancy_per_trade"))
    break_even_cost = _optional_number(complete.get("break_even_transaction_cost_per_trade"))

    yearly = _consistency_snapshot(_mapping(consistency, "yearly"))
    monthly = _consistency_snapshot(_mapping(consistency, "monthly"))
    quarterly = _partition_snapshot(_sequence(summaries, "by_quarter"))
    directions = _partition_snapshot(_sequence(summaries, "by_direction"))
    sessions = _partition_snapshot(_sequence(summaries, "by_session"))
    volatility_snapshot = _partition_snapshot(
        _sequence(summaries, "by_volatility_regime")
    )
    strongest_month = _mapping(_mapping(concentration, "strongest_month"), "net")
    strongest_year = _mapping(_mapping(concentration, "strongest_year"), "net")
    top_ten = _top_fraction(_sequence(concentration, "net_by_top_trades"), 0.10)
    volatility = [
        {"regime": item["group"], **{key: value for key, value in item.items() if key != "group"}}
        for item in volatility_snapshot["groups"]
    ]
    failure = _failure_mechanism(
        complete,
        trade_count=trade_count,
        gross=gross,
        net=net,
        yearly=yearly,
        monthly=monthly,
        strongest_month=strongest_month,
        top_ten=top_ten,
        net_interval=_mapping(bootstrap, "net_expectancy_per_trade"),
        volatility=volatility,
    )
    return {
        "strategy": strategy,
        "economics": {
            "trade_count": trade_count,
            "total_lots": total_lots,
            "gross_pnl": gross,
            "net_pnl": net,
            "gross_expectancy_per_trade": gross_expectancy,
            "net_expectancy_per_trade": net_expectancy,
        },
        "costs": {
            "total_spread_cost": spread,
            "total_slippage_cost": slippage,
            "total_commission": commission,
            "total_transaction_cost": total_cost,
            "spread_cost_per_trade": spread / divisor if divisor else None,
            "slippage_cost_per_trade": slippage / divisor if divisor else None,
            "commission_per_trade": commission / divisor if divisor else None,
            "transaction_cost_per_trade": cost_per_trade,
            "cost_to_positive_gross_edge_ratio": (
                total_cost / gross if gross > 0 else None
            ),
        },
        "break_even": {
            "transaction_cost_per_trade": break_even_cost,
            "spread_points": _optional_number(complete.get("break_even_spread_points")),
            "commission_per_lot_per_side": commission_break_even,
            "cost_headroom_per_trade": (
                break_even_cost - cost_per_trade
                if break_even_cost is not None and cost_per_trade is not None
                else None
            ),
        },
        "uncertainty": {
            "gross_expectancy_per_trade": _mapping(
                bootstrap, "gross_expectancy_per_trade"
            ),
            "net_expectancy_per_trade": _mapping(
                bootstrap, "net_expectancy_per_trade"
            ),
            "profit_factor": _mapping(bootstrap, "profit_factor"),
            "maximum_drawdown": _mapping(bootstrap, "maximum_drawdown"),
            "downside_tail": _mapping(statistics, "downside_tail"),
        },
        "profit_concentration": {
            "top_ten_percent_net": top_ten,
            "strongest_month_net": dict(strongest_month),
            "strongest_year_net": dict(strongest_year),
            "top_trade_basis": concentration.get("top_trade_basis"),
            "strongest_period_basis": concentration.get("strongest_period_basis"),
        },
        "temporal_stability": {
            "yearly": yearly,
            "quarterly": quarterly,
            "monthly": monthly,
            "directions": directions,
            "sessions": sessions,
            "volatility_regimes": volatility_snapshot,
            "attribution_basis": row.get("attribution_basis"),
            "session_definition": row.get("session_definition"),
            "volatility_regime_definition": row.get("volatility_regime_definition"),
        },
        "failure_mechanism": failure,
        "rejections": {
            "count": _integer(complete, "rejected_intent_count"),
            "reason_counts": dict(complete.get("rejected_intent_reason_counts", {})),
        },
    }


def _partition_snapshot(rows: Sequence[object]) -> dict[str, object]:
    groups = [
        {
            "group": str(row["group"]),
            "trade_count": _integer(row, "trade_count"),
            "gross_pnl": _number(row, "gross_pnl"),
            "total_transaction_cost": _number(row, "total_transaction_cost"),
            "net_pnl": _number(row, "net_pnl"),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    active = [row for row in groups if int(row["trade_count"]) > 0]
    positive = [row for row in active if float(row["net_pnl"]) > 0]
    strongest = max(active, key=lambda row: float(row["net_pnl"])) if active else None
    weakest = min(active, key=lambda row: float(row["net_pnl"])) if active else None
    return {
        "group_count": len(groups),
        "active_group_count": len(active),
        "positive_active_group_count": len(positive),
        "positive_active_group_fraction": (
            len(positive) / len(active) if active else None
        ),
        "strongest_group": strongest,
        "weakest_group": weakest,
        "groups": groups,
    }

def _failure_mechanism(
    complete: Mapping[str, object],
    *,
    trade_count: int,
    gross: float,
    net: float,
    yearly: Mapping[str, object],
    monthly: Mapping[str, object],
    strongest_month: Mapping[str, object],
    top_ten: Mapping[str, object] | None,
    net_interval: Mapping[str, object],
    volatility: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    reason_counts_value = complete.get("rejected_intent_reason_counts", {})
    reason_counts = reason_counts_value if isinstance(reason_counts_value, dict) else {}
    censoring_phrases = (
        "daily loss",
        "weekly loss",
        "drawdown",
        "consecutive losses",
        "trades per hour",
        "trades per day",
    )
    censoring_count = sum(
        int(count)
        for reason, count in reason_counts.items()
        if any(phrase in str(reason).lower() for phrase in censoring_phrases)
    )
    minimum_volume_count = sum(
        int(count)
        for reason, count in reason_counts.items()
        if "below the broker minimum volume" in str(reason).lower()
    )
    yearly_fraction = _optional_number(yearly.get("positive_active_period_fraction"))
    monthly_fraction = _optional_number(monthly.get("positive_active_period_fraction"))
    month_concentration = _optional_number(strongest_month.get("contribution_fraction"))
    top_ten_concentration = (
        _optional_number(top_ten.get("contribution_fraction")) if top_ten else None
    )
    temporal_instability = (
        (yearly_fraction is not None and yearly_fraction < MINIMUM_POSITIVE_YEAR_FRACTION)
        or (monthly_fraction is not None and monthly_fraction < MINIMUM_POSITIVE_MONTH_FRACTION)
        or (
            month_concentration is not None
            and month_concentration > MAX_STRONGEST_MONTH_CONTRIBUTION
        )
        or (
            top_ten_concentration is not None
            and top_ten_concentration > MAX_TOP_TEN_TRADE_CONTRIBUTION
        )
    )
    active_regimes = [row for row in volatility if int(row.get("trade_count") or 0) > 0]
    regime_signs = {float(row.get("net_pnl") or 0) > 0 for row in active_regimes}
    regime_instability = len(regime_signs) > 1
    lower = _optional_number(net_interval.get("lower"))
    upper = _optional_number(net_interval.get("upper"))
    uncertainty = lower is None or upper is None or lower <= 0 <= upper

    contributors: list[str] = []
    if censoring_count:
        contributors.append("RISK_CENSORSHIP")
    if minimum_volume_count:
        contributors.append("CAPITAL_DEPLETION_OR_MINIMUM_VOLUME")
    if trade_count < MINIMUM_DIAGNOSTIC_TRADES:
        contributors.append("INSUFFICIENT_SAMPLE")
    if gross <= 0:
        contributors.append("SIGNAL_QUALITY")
    if gross > 0 and net <= 0:
        contributors.append("TRANSACTION_COSTS")
    if temporal_instability or regime_instability:
        contributors.append("TEMPORAL_OR_REGIME_INSTABILITY")
    if uncertainty:
        contributors.append("STATISTICAL_UNCERTAINTY")

    if censoring_count:
        dominant = "RISK_CENSORSHIP"
    elif trade_count < MINIMUM_DIAGNOSTIC_TRADES:
        dominant = "INSUFFICIENT_SAMPLE"
    elif gross <= 0:
        dominant = "SIGNAL_QUALITY"
    elif net <= 0:
        dominant = "TRANSACTION_COSTS"
    elif temporal_instability or regime_instability:
        dominant = "TEMPORAL_OR_REGIME_INSTABILITY"
    elif uncertainty:
        dominant = "STATISTICAL_UNCERTAINTY"
    else:
        dominant = "NO_DOMINANT_FAILURE_DETECTED"
    return {
        "dominant": dominant,
        "contributors": contributors,
        "evidence": {
            "risk_censoring_rejection_count": censoring_count,
            "minimum_volume_rejection_count": minimum_volume_count,
            "trade_count": trade_count,
            "gross_pnl": gross,
            "net_pnl": net,
            "positive_active_year_fraction": yearly_fraction,
            "positive_active_month_fraction": monthly_fraction,
            "strongest_month_net_contribution_fraction": month_concentration,
            "top_ten_percent_trade_net_contribution_fraction": top_ten_concentration,
            "mixed_volatility_regime_signs": regime_instability,
            "net_expectancy_ci_lower": lower,
        },
        "interpretation_limit": "classification is diagnostic and is not a deployment approval",
    }


def _consistency_snapshot(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "period_count": value.get("period_count"),
        "active_period_count": value.get("active_period_count"),
        "positive_period_count": value.get("positive_period_count"),
        "negative_period_count": value.get("negative_period_count"),
        "positive_period_fraction": value.get("positive_period_fraction"),
        "positive_active_period_fraction": value.get("positive_active_period_fraction"),
        "strongest_period": value.get("strongest_period"),
        "weakest_period": value.get("weakest_period"),
        "periods": value.get("periods"),
    }


def _top_fraction(
    rows: Sequence[object], target: float
) -> dict[str, object] | None:
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return None
    exact = [
        row
        for row in candidates
        if isclose(_number(row, "top_trade_fraction"), target, abs_tol=1e-12)
    ]
    return dict(exact[0]) if exact else None


def _caveats(report: Mapping[str, Any]) -> list[str]:
    manifest = _mapping(report, "run_manifest")
    frozen = _mapping(manifest, "frozen")
    costs = _mapping(frozen, "transaction_costs")
    commission_model = _mapping(costs, "commission_model")
    first = report["results"][0]
    methodology = _mapping(_mapping(first, "statistical_robustness"), "methodology")
    settings = _mapping(methodology, "settings")
    return [
        "Development-only evidence: [2019-01-01, 2024-01-01); 2024-2026 is not used.",
        (
            "Costs are fixed assumptions: "
            f"spread {costs.get('spread_points')} points, slippage {costs.get('slippage_points')} points, "
            f"commission {commission_model.get('amount')} per lot per side."
        ),
        "Execution is simulated from M1 OHLC candles, not tick replay; variable spread, latency, partial fills, and intrabar path remain unmodeled.",
        (
            "Bootstrap diagnostics use IID completed-trade resampling with PCG64 seed "
            f"{settings.get('random_seed')} and {settings.get('bootstrap_samples')} samples; serial dependence is not preserved."
        ),
        "Calendar, session, and volatility diagnostics are attributed at trade entry; they do not modify strategy rules.",
        "Profit concentration denominators are positive-profit pools, not signed aggregate PnL.",
        "The research profile retains equity-based sizing and broker minimum volume; losses can reduce later exposure, so calendar results are portfolio-survival evidence rather than constant-notional signal estimates.",
        "The assessment is diagnostic only and provides neither deployment approval nor a new strategy proposal.",
    ]


def _markdown(machine: Mapping[str, Any]) -> str:
    strategies = machine["strategies"]
    lines = [
        "# Continuous Development Diagnosis",
        "",
        (
            f"Source: `{machine['source']['label']}`  "
            f"Run: `{machine['source']['run_id']}`  "
            f"Scope: 2019-2023 development only"
        ),
        "",
        "| Strategy | Trades | Gross PnL | Costs | Net PnL | Gross/trade | Cost/trade | Net/trade | Dominant mechanism |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in strategies:
        economics, costs = row["economics"], row["costs"]
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row["strategy"]),
                    str(economics["trade_count"]),
                    _money(economics["gross_pnl"]),
                    _money(costs["total_transaction_cost"]),
                    _money(economics["net_pnl"]),
                    _money(economics["gross_expectancy_per_trade"]),
                    _money(costs["transaction_cost_per_trade"]),
                    _money(economics["net_expectancy_per_trade"]),
                    str(row["failure_mechanism"]["dominant"]),
                )
            )
            + " |"
        )

    sections = (
        ("1. Gross Edge", _gross_markdown),
        ("2. Exact Cost Decomposition", _cost_markdown),
        ("3. Average Gross Edge Per Trade", _gross_average_markdown),
        ("4. Transaction Cost Per Trade", _cost_average_markdown),
        ("5. Break-Even Cost Levels", _break_even_markdown),
        ("6. Profit Concentration", _concentration_markdown),
        ("7. Temporal Stability", _temporal_markdown),
        ("8. Dominant Failure Mechanism", _failure_markdown),
    )
    for title, render in sections:
        lines.extend(("", f"## {title}"))
        lines.extend(render(row) for row in strategies)
    lines.extend(("", "## Methodological Caveats"))
    lines.extend(f"- {item}" for item in machine["caveats"])
    lines.extend(
        (
            "",
            "No strategy is approved for deployment. This assessment does not propose a new strategy.",
            "",
        )
    )
    return "\n".join(lines)


def _gross_markdown(row: Mapping[str, Any]) -> str:
    interval = row["uncertainty"]["gross_expectancy_per_trade"]
    return (
        f"- `{row['strategy']}`: gross {_money(row['economics']['gross_pnl'])}; "
        f"bootstrap gross expectancy CI [{_money(interval.get('lower'))}, {_money(interval.get('upper'))}]."
    )


def _cost_markdown(row: Mapping[str, Any]) -> str:
    costs = row["costs"]
    return (
        f"- `{row['strategy']}`: spread {_money(costs['total_spread_cost'])}, "
        f"slippage {_money(costs['total_slippage_cost'])}, commission {_money(costs['total_commission'])}, "
        f"total {_money(costs['total_transaction_cost'])}."
    )


def _gross_average_markdown(row: Mapping[str, Any]) -> str:
    return f"- `{row['strategy']}`: {_money(row['economics']['gross_expectancy_per_trade'])} per trade."


def _cost_average_markdown(row: Mapping[str, Any]) -> str:
    return f"- `{row['strategy']}`: {_money(row['costs']['transaction_cost_per_trade'])} per trade."


def _break_even_markdown(row: Mapping[str, Any]) -> str:
    value = row["break_even"]
    return (
        f"- `{row['strategy']}`: all-in {_money(value['transaction_cost_per_trade'])}/trade; "
        f"spread {_plain(value['spread_points'])} points; commission {_money(value['commission_per_lot_per_side'])}/lot/side; "
        f"headroom {_money(value['cost_headroom_per_trade'])}/trade."
    )


def _concentration_markdown(row: Mapping[str, Any]) -> str:
    value = row["profit_concentration"]
    top = value["top_ten_percent_net"] or {}
    month = value["strongest_month_net"]
    return (
        f"- `{row['strategy']}`: top 10% trades {_percent(top.get('contribution_fraction'))}; "
        f"strongest month `{month.get('period')}` {_percent(month.get('contribution_fraction'))}."
    )


def _temporal_markdown(row: Mapping[str, Any]) -> str:
    value = row["temporal_stability"]
    return (
        f"- `{row['strategy']}`: positive active years {_percent(value['yearly'].get('positive_active_period_fraction'))}; "
        f"quarters {_percent(value['quarterly'].get('positive_active_group_fraction'))}; "
        f"months {_percent(value['monthly'].get('positive_active_period_fraction'))}; "
        f"best/worst month `{_period_name(value['monthly'].get('strongest_period'))}`/"
        f"`{_period_name(value['monthly'].get('weakest_period'))}`; "
        f"best direction {_group_net(value['directions'].get('strongest_group'))}; "
        f"best DST-aware session {_group_net(value['sessions'].get('strongest_group'))}."
    )


def _failure_markdown(row: Mapping[str, Any]) -> str:
    failure = row["failure_mechanism"]
    contributors = ", ".join(failure["contributors"]) or "none"
    minimum_volume = failure["evidence"].get("minimum_volume_rejection_count", 0)
    suffix = f"; minimum-volume rejections: {minimum_volume}" if minimum_volume else ""
    return f"- `{row['strategy']}`: **{failure['dominant']}**; contributors: {contributors}{suffix}."


def _mapping(value: Mapping[str, object], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ContinuousAssessmentError(f"required object field is missing: {key}")
    return dict(item)


def _sequence(value: Mapping[str, object], key: str) -> list[object]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ContinuousAssessmentError(f"required array field is missing: {key}")
    return item


def _number(value: Mapping[str, object], key: str) -> float:
    if key not in value:
        raise ContinuousAssessmentError(f"required numeric field is missing: {key}")
    result = _optional_number(value[key])
    if result is None:
        raise ContinuousAssessmentError(f"required numeric field is null or invalid: {key}")
    return result


def _integer(value: Mapping[str, object], key: str) -> int:
    number = _number(value, key)
    if number < 0 or not number.is_integer():
        raise ContinuousAssessmentError(f"required count field is invalid: {key}")
    return int(number)


def _optional_number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _money(value: object) -> str:
    number = _optional_number(value)
    return "n/a" if number is None else f"{number:,.2f}"


def _plain(value: object) -> str:
    number = _optional_number(value)
    return "n/a" if number is None else f"{number:.4g}"


def _percent(value: object) -> str:
    number = _optional_number(value)
    return "n/a" if number is None else f"{number * 100:.1f}%"


def _period_name(value: object) -> str:
    return str(value.get("period")) if isinstance(value, dict) else "n/a"


def _group_net(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    return f"`{value.get('group')}` ({_money(value.get('net_pnl'))})"

def _markdown_text(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
