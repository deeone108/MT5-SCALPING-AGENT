"""Constant-exposure diagnostics that separate raw signal economics from sizing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from math import fsum, isclose
from typing import Any

import numpy as np
import pandas as pd

from mt5_scalping_agent.backtesting import BacktestResult, BacktestTrade
from mt5_scalping_agent.data.sessions import (
    NEW_YORK_SESSION_SUBSECTIONS,
    new_york_session_subsection,
)
from mt5_scalping_agent.research.continuous_evaluation import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    VolatilityRegimeSettings,
    continuous_result_report,
)
from mt5_scalping_agent.research.statistical_robustness import (
    StatisticalRobustnessSettings,
)
from mt5_scalping_agent.risk import SymbolRiskSpec


DEFAULT_PIP_SIZE = 0.0001
DIRECTION_LABELS = ("BUY", "SELL")
VOLATILITY_LABELS = ("low", "normal", "high", "unavailable")


def signal_economics_report(
    result: BacktestResult,
    candles: pd.DataFrame,
    *,
    strategy_name: str,
    fixed_volume_lots: float,
    symbol: SymbolRiskSpec,
    initial_balance: float = 10_000.0,
    period_start: datetime = DEVELOPMENT_START,
    period_end: datetime = DEVELOPMENT_END,
    pip_size: float = DEFAULT_PIP_SIZE,
    account_currency: str = "USD",
    volatility_settings: VolatilityRegimeSettings = VolatilityRegimeSettings(),
    statistical_settings: StatisticalRobustnessSettings = StatisticalRobustnessSettings(),
    precomputed_volatility: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Build a deterministic fixed-lot signal-opportunity report.

    A signal is one strategy intent that passes the preserved plan and broker
    constraints and becomes a completed fixed-lot simulated trade. Rejected
    intents are reported separately. The candle engine remains single-position,
    so it does not ask the strategy for overlapping signals while a trade or
    next-candle intent is active.
    """
    if not strategy_name.strip():
        raise ValueError("strategy_name must not be empty")
    if fixed_volume_lots <= 0:
        raise ValueError("fixed_volume_lots must be positive")
    if initial_balance <= 0:
        raise ValueError("initial_balance must be positive")
    if pip_size <= 0:
        raise ValueError("pip_size must be positive")
    if not account_currency.strip():
        raise ValueError("account_currency must not be empty")
    for trade in result.trades:
        if not isclose(
            trade.volume_lots,
            fixed_volume_lots,
            rel_tol=0.0,
            abs_tol=1e-10,
        ):
            raise ValueError(
                "constant-exposure report requires every executed trade to use "
                "fixed_volume_lots"
            )

    base = continuous_result_report(
        result,
        candles,
        period_start=period_start,
        period_end=period_end,
        initial_balance=initial_balance,
        symbol=symbol.symbol,
        volatility_settings=volatility_settings,
        statistical_settings=statistical_settings,
        precomputed_volatility=precomputed_volatility,
    )
    pip_value_per_lot = pip_size / symbol.tick_size * symbol.tick_value
    records = [
        _signal_record(
            trade,
            record,
            pip_value_per_lot=pip_value_per_lot,
            pip_size=pip_size,
        )
        for trade, record in zip(result.trades, base["trades"], strict=True)
    ]
    economics = _economics_sections(
        records,
        period_start=period_start,
        period_end=period_end,
    )
    rejection_reasons = Counter(
        reason.strip()
        for rejection in result.rejected_intents
        for reason in rejection.split(";")
        if reason.strip()
    )
    residual = economics["complete"]["accounting_identity_residual"]
    return {
        "analysis_kind": "constant_exposure_signal_economics",
        "strategy": strategy_name,
        "period": base["period"],
        "attribution_basis": base["attribution_basis"],
        "session_definition": base["session_definition"],
        "volatility_regime_definition": base["volatility_regime_definition"],
        "sizing_definition": {
            "mode": "research_fixed_lot",
            "fixed_volume_lots": fixed_volume_lots,
            "account_equity_affects_volume": False,
            "portfolio_loss_circuit_breakers_affect_entries": False,
            "preserved_constraints": [
                "single-position simulation",
                "valid directional stop and target",
                "symbol match",
                "spread ceiling",
                "market-data freshness",
                "minimum reward/risk",
                "broker lot minimum, maximum, and step",
                "open-position and exposure limits",
            ],
        },
        "unit_definitions": {
            "account_currency": account_currency,
            "pip_size": pip_size,
            "pip_value_per_standard_lot": pip_value_per_lot,
            "pip_conversion": (
                "monetary value / (pip value per standard lot * executed lots)"
            ),
            "mae_sign": "zero or negative; adverse magnitude is reported separately",
            "mfe_sign": "zero or positive",
        },
        "signal_definition": {
            "signal_count": len(records),
            "meaning": "executed and completed fixed-lot simulated trades",
            "rejected_intent_count": len(result.rejected_intents),
            "rejected_intent_reason_counts": dict(sorted(rejection_reasons.items())),
            "overlapping_signals_observed": False,
            "overlap_note": (
                "The single-position engine does not query the strategy while a position "
                "or pending next-candle intent is active."
            ),
        },
        # Preserve the canonical shape used by continuous registry evidence.
        "summaries": base["summaries"],
        "signal_economics": economics,
        "statistical_robustness": base["statistical_robustness"],
        "accounting_audit": {
            "gross_minus_cost_equals_net": isclose(
                float(residual), 0.0, rel_tol=1e-12, abs_tol=1e-9
            ),
            "residual": residual,
        },
        "limitations": [
            "Planned stop and target distances are measured from the friction-free next-bar reference opening quote.",
            "MFE and MAE are gross excursions from the reference opening quote, before costs.",
            "Excursions use M1 candle highs and lows, including the exit candle; intrabar path and stop/target ordering are unknown.",
            "Executed signal count excludes rejected intents and does not include overlapping opportunities suppressed by the single-position engine.",
            "Fixed spread, slippage, and commission are research assumptions, not tick replay or execution evidence.",
            "Volatility and session labels are diagnostic only and do not change strategy rules.",
        ],
        "trades": records,
    }


def _signal_record(
    trade: BacktestTrade,
    record: Mapping[str, Any],
    *,
    pip_value_per_lot: float,
    pip_size: float,
) -> dict[str, Any]:
    if pip_value_per_lot <= 0 or trade.volume_lots <= 0:
        raise ValueError("pip conversion requires positive pip value and volume")
    divisor = pip_value_per_lot * trade.volume_lots
    mfe = float(trade.mfe) if trade.mfe is not None else None
    mae = float(trade.mae) if trade.mae is not None else None
    cost = float(trade.total_transaction_cost or 0.0)
    value_per_price_unit = divisor / pip_size
    stored_reference = getattr(trade, "reference_entry_price", None)
    reference_entry_price = (
        float(stored_reference)
        if stored_reference is not None
        else (
            trade.entry_price
            - (trade.spread_cost + trade.slippage_cost) / value_per_price_unit
            if trade.direction.value == "BUY"
            else trade.entry_price + trade.slippage_cost / value_per_price_unit
        )
    )
    stop_distance_pips = (
        abs(reference_entry_price - trade.stop_price) / pip_size
        if trade.stop_price is not None
        else None
    )
    target_distance_pips = (
        abs(reference_entry_price - trade.target_price) / pip_size
        if trade.target_price is not None
        else None
    )
    labels = dict(record.get("diagnostic_labels", {}))
    labels["new_york_session_subsection"] = new_york_session_subsection(
        _as_utc(trade.entry_time)
    )
    cost_pips = cost / divisor
    normalized = {
        "gross_pnl_usd": trade.gross_pnl,
        "gross_pips": trade.gross_pnl / divisor,
        "spread_cost_usd": trade.spread_cost,
        "spread_cost_pips": trade.spread_cost / divisor,
        "slippage_cost_usd": trade.slippage_cost,
        "slippage_cost_pips": trade.slippage_cost / divisor,
        "commission_usd": trade.commission,
        "commission_pips": trade.commission / divisor,
        "total_transaction_cost_usd": cost,
        "total_transaction_cost_pips": cost_pips,
        "net_pnl_usd": trade.net_pnl,
        "net_pips": trade.net_pnl / divisor,
        "mfe_usd": mfe,
        "mfe_pips": mfe / divisor if mfe is not None else None,
        "mae_signed_usd": mae,
        "mae_signed_pips": mae / divisor if mae is not None else None,
        "mae_adverse_magnitude_usd": -mae if mae is not None else None,
        "mae_adverse_magnitude_pips": -mae / divisor if mae is not None else None,
        "planned_stop_distance_pips": stop_distance_pips,
        "planned_target_distance_pips": target_distance_pips,
        "cost_to_planned_stop_ratio": (
            cost / divisor / stop_distance_pips
            if stop_distance_pips is not None and stop_distance_pips > 0
            else None
        ),
        "cost_to_planned_target_ratio": (
            cost_pips / target_distance_pips
            if target_distance_pips is not None and target_distance_pips > 0
            else None
        ),
        "planned_stop_to_cost_ratio": (
            stop_distance_pips / cost_pips
            if stop_distance_pips is not None and cost_pips > 0
            else None
        ),
        "planned_target_to_cost_ratio": (
            target_distance_pips / cost_pips
            if target_distance_pips is not None and cost_pips > 0
            else None
        ),
        "planned_reward_risk_ratio": (
            target_distance_pips / stop_distance_pips
            if target_distance_pips is not None
            and stop_distance_pips is not None
            and stop_distance_pips > 0
            else None
        ),
        "cost_adjusted_planned_reward_risk_ratio": (
            (target_distance_pips - cost_pips) / (stop_distance_pips + cost_pips)
            if target_distance_pips is not None
            and stop_distance_pips is not None
            and stop_distance_pips + cost_pips > 0
            else None
        ),
        "holding_duration_minutes": (
            trade.holding_duration.total_seconds() / 60.0
            if trade.holding_duration is not None
            else None
        ),
        "mfe_exceeds_1x_cost": mfe is not None and mfe > cost,
        "mfe_exceeds_2x_cost": mfe is not None and mfe > 2.0 * cost,
        "mfe_exceeds_3x_cost": mfe is not None and mfe > 3.0 * cost,
    }
    return {**record, "diagnostic_labels": labels, "signal_economics": normalized}


def _economics_sections(
    records: Sequence[Mapping[str, Any]],
    *,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, object]:
    years = [f"{year:04d}" for year in range(period_start.year, period_end.year)]
    months = list(
        pd.period_range(
            pd.Timestamp(period_start).tz_localize(None).to_period("M"),
            pd.Timestamp(period_end - timedelta(microseconds=1))
            .tz_localize(None)
            .to_period("M"),
            freq="M",
        ).astype(str)
    )
    by_year = _group_summaries(records, "year", years)
    by_month = _group_summaries(records, "month", months)
    midpoint = period_start + (period_end - period_start) / 2
    halves = (
        ("first_half", period_start, midpoint),
        ("second_half", midpoint, period_end),
    )
    by_half = [
        {
            "group": label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            **_economics_summary(
                [
                    row
                    for row in records
                    if start <= _record_entry(row) < end
                ]
            ),
        }
        for label, start, end in halves
    ]
    return {
        "complete": _economics_summary(records),
        "by_year": by_year,
        "by_month": by_month,
        "by_causal_volatility_regime": _group_summaries(
            records, "volatility_regime", VOLATILITY_LABELS
        ),
        "by_new_york_local_subsection": _group_summaries(
            records,
            "new_york_session_subsection",
            NEW_YORK_SESSION_SUBSECTIONS,
        ),
        "by_direction": _group_summaries(records, "direction", DIRECTION_LABELS),
        "temporal_decay": _temporal_decay(by_year, by_month, by_half),
    }


def _group_summaries(
    records: Sequence[Mapping[str, Any]],
    label: str,
    expected_groups: Sequence[str],
) -> list[dict[str, object]]:
    observed = {
        str(_labels(row).get(label, "unavailable"))
        for row in records
    }
    groups = list(
        dict.fromkeys((*expected_groups, *sorted(observed.difference(expected_groups))))
    )
    return [
        {
            "group": group,
            **_economics_summary(
                [row for row in records if str(_labels(row).get(label)) == group]
            ),
        }
        for group in groups
    ]


def _economics_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    economics = [row["signal_economics"] for row in records]
    signal_count = len(economics)
    gross_usd = [float(row["gross_pnl_usd"]) for row in economics]
    gross_pips = [float(row["gross_pips"]) for row in economics]
    spread_usd = [float(row["spread_cost_usd"]) for row in economics]
    slippage_usd = [float(row["slippage_cost_usd"]) for row in economics]
    commission_usd = [float(row["commission_usd"]) for row in economics]
    cost_usd = [float(row["total_transaction_cost_usd"]) for row in economics]
    cost_pips = [float(row["total_transaction_cost_pips"]) for row in economics]
    net_usd = [float(row["net_pnl_usd"]) for row in economics]
    net_pips = [float(row["net_pips"]) for row in economics]
    mfe_usd = [float(row["mfe_usd"]) for row in economics if row["mfe_usd"] is not None]
    mfe_pips = [float(row["mfe_pips"]) for row in economics if row["mfe_pips"] is not None]
    mae_usd = [
        float(row["mae_signed_usd"])
        for row in economics
        if row["mae_signed_usd"] is not None
    ]
    mae_pips = [
        float(row["mae_signed_pips"])
        for row in economics
        if row["mae_signed_pips"] is not None
    ]
    adverse_usd = [-value for value in mae_usd]
    adverse_pips = [-value for value in mae_pips]
    stop_pips = [
        float(row["planned_stop_distance_pips"])
        for row in economics
        if row["planned_stop_distance_pips"] is not None
    ]
    target_pips = [
        float(row["planned_target_distance_pips"])
        for row in economics
        if row["planned_target_distance_pips"] is not None
    ]
    cost_stop_ratios = [
        float(row["cost_to_planned_stop_ratio"])
        for row in economics
        if row["cost_to_planned_stop_ratio"] is not None
    ]
    cost_target_ratios = [
        float(row["cost_to_planned_target_ratio"])
        for row in economics
        if row["cost_to_planned_target_ratio"] is not None
    ]
    stop_cost_ratios = [
        float(row["planned_stop_to_cost_ratio"])
        for row in economics
        if row["planned_stop_to_cost_ratio"] is not None
    ]
    target_cost_ratios = [
        float(row["planned_target_to_cost_ratio"])
        for row in economics
        if row["planned_target_to_cost_ratio"] is not None
    ]
    planned_reward_risk = [
        float(row["planned_reward_risk_ratio"])
        for row in economics
        if row["planned_reward_risk_ratio"] is not None
    ]
    adjusted_reward_risk = [
        float(row["cost_adjusted_planned_reward_risk_ratio"])
        for row in economics
        if row["cost_adjusted_planned_reward_risk_ratio"] is not None
    ]
    holding_minutes = [
        float(row["holding_duration_minutes"])
        for row in economics
        if row["holding_duration_minutes"] is not None
    ]
    gross_total = fsum(gross_usd)
    cost_total = fsum(cost_usd)
    net_total = fsum(net_usd)
    mean_mfe = _mean(mfe_usd)
    mean_cost = _mean(cost_usd)
    return {
        "signal_count": signal_count,
        "gross": {
            "total_usd": gross_total,
            "expectancy_usd_per_signal": _mean(gross_usd),
            "total_pips": fsum(gross_pips),
            "expectancy_pips_per_signal": _mean(gross_pips),
        },
        "costs": {
            "spread_total_usd": fsum(spread_usd),
            "slippage_total_usd": fsum(slippage_usd),
            "commission_total_usd": fsum(commission_usd),
            "all_in_total_usd": cost_total,
            "all_in_expectancy_usd_per_signal": mean_cost,
            "all_in_total_pips": fsum(cost_pips),
            "all_in_expectancy_pips_per_signal": _mean(cost_pips),
            "distribution_usd": _distribution(cost_usd),
            "distribution_pips": _distribution(cost_pips),
        },
        "net": {
            "total_usd": net_total,
            "expectancy_usd_per_signal": _mean(net_usd),
            "total_pips": fsum(net_pips),
            "expectancy_pips_per_signal": _mean(net_pips),
        },
        "mfe": {
            "observation_count": len(mfe_usd),
            "missing_count": signal_count - len(mfe_usd),
            "distribution_usd": _distribution(mfe_usd),
            "distribution_pips": _distribution(mfe_pips),
        },
        "mae": {
            "observation_count": len(mae_usd),
            "missing_count": signal_count - len(mae_usd),
            "signed_distribution_usd": _distribution(mae_usd),
            "signed_distribution_pips": _distribution(mae_pips),
            "adverse_magnitude_distribution_usd": _distribution(adverse_usd),
            "adverse_magnitude_distribution_pips": _distribution(adverse_pips),
        },
        "planned_distances": {
            "stop_distance_pips": _distribution(stop_pips),
            "target_distance_pips": _distribution(target_pips),
            "cost_to_stop_ratio": _distribution(cost_stop_ratios),
            "cost_to_target_ratio": _distribution(cost_target_ratios),
            "stop_to_cost_ratio": _distribution(stop_cost_ratios),
            "target_to_cost_ratio": _distribution(target_cost_ratios),
            "planned_reward_risk_ratio": _distribution(planned_reward_risk),
            "cost_adjusted_planned_reward_risk_ratio": _distribution(
                adjusted_reward_risk
            ),
        },
        "holding_duration_minutes": _distribution(holding_minutes),
        "mfe_cost_multiples": _mfe_cost_multiples(economics),
        "opportunity_vs_friction": {
            "mean_mfe_usd": mean_mfe,
            "mean_mfe_pips": _mean(mfe_pips),
            "median_mfe_usd": _median(mfe_usd),
            "median_mfe_pips": _median(mfe_pips),
            "mean_all_in_cost_usd": mean_cost,
            "mean_all_in_cost_pips": _mean(cost_pips),
            "mean_mfe_to_mean_cost_ratio": _ratio(mean_mfe, mean_cost),
            "gross_expectancy_to_mean_cost_ratio": _ratio(
                _mean(gross_usd), mean_cost
            ),
            "gross_capture_efficiency_of_mean_mfe": _ratio(
                _mean(gross_usd), mean_mfe
            ),
        },
        "accounting_identity_residual": gross_total - cost_total - net_total,
    }


def _mfe_cost_multiples(economics: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    observed = [row for row in economics if row["mfe_usd"] is not None]
    count = len(observed)
    output: dict[str, object] = {"observation_count": count}
    for multiple in (1, 2, 3):
        greater = sum(
            float(row["mfe_usd"])
            > multiple * float(row["total_transaction_cost_usd"])
            for row in observed
        )
        output[f"strictly_exceeds_{multiple}x_cost_count"] = greater
        output[f"strictly_exceeds_{multiple}x_cost_percent"] = (
            100.0 * greater / count if count else None
        )
    return output


def _distribution(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "maximum": None,
            "mean": None,
        }
    array = np.asarray(values, dtype=np.float64)
    quantiles = np.quantile(array, (0.05, 0.25, 0.50, 0.75, 0.95), method="linear")
    return {
        "count": len(values),
        "minimum": float(array.min()),
        "p05": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "median": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p95": float(quantiles[4]),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
    }


def _temporal_decay(
    by_year: Sequence[Mapping[str, Any]],
    by_month: Sequence[Mapping[str, Any]],
    by_half: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    annual_points = _active_expectancy_points(by_year)
    monthly_points = _active_expectancy_points(by_month)
    first = by_half[0]["gross"]["expectancy_pips_per_signal"]
    second = by_half[1]["gross"]["expectancy_pips_per_signal"]
    annual_slope = _linear_slope([point[1] for point in annual_points])
    monthly_slope = _linear_slope([point[1] for point in monthly_points])
    return {
        "calendar_halves": list(by_half),
        "annual_active_period_count": len(annual_points),
        "annual_gross_expectancy_pips_slope_per_year": annual_slope,
        "monthly_active_period_count": len(monthly_points),
        "monthly_gross_expectancy_pips_slope_per_active_month": monthly_slope,
        "first_half_gross_expectancy_pips_per_signal": first,
        "second_half_gross_expectancy_pips_per_signal": second,
        "second_minus_first_half_pips_per_signal": (
            float(second) - float(first)
            if first is not None and second is not None
            else None
        ),
        "raw_signal_quality_deteriorated": (
            bool(float(second) < float(first) and annual_slope is not None and annual_slope < 0)
            if first is not None and second is not None and annual_slope is not None
            else None
        ),
        "interpretation_rule": (
            "true only when second-half gross expectancy is lower than first-half "
            "and the active-year gross-expectancy slope is negative"
        ),
    }


def _active_expectancy_points(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[str, float]]:
    output: list[tuple[str, float]] = []
    for row in rows:
        value = row["gross"]["expectancy_pips_per_signal"]
        if value is not None:
            output.append((str(row["group"]), float(value)))
    return output


def _linear_slope(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    x = np.arange(len(values), dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    centered = x - x.mean()
    denominator = float(np.dot(centered, centered))
    return float(np.dot(centered, y - y.mean()) / denominator)


def _mean(values: Sequence[float]) -> float | None:
    return fsum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(np.median(np.asarray(values, dtype=np.float64))) if values else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _labels(record: Mapping[str, Any]) -> Mapping[str, Any]:
    labels = record.get("diagnostic_labels")
    return labels if isinstance(labels, Mapping) else {}


def _record_entry(record: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(record["entry_time"])).astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("trade timestamps must be timezone-aware")
    return value.astimezone(UTC)