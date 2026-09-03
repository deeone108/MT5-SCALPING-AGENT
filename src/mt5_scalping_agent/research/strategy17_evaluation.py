"""Strategy 17 gate evaluation and serial-dependence diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from math import ceil, isfinite
from typing import Any

import numpy as np

from mt5_scalping_agent.backtesting import BacktestTrade
from mt5_scalping_agent.research.continuous_evaluation import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    SplitIsolationError,
    assert_development_period,
)
from mt5_scalping_agent.research.registry import EconomicPromotionGate
from mt5_scalping_agent.risk import SymbolRiskSpec


DEFAULT_BLOCK_BOOTSTRAP_SEED = 20_260_824


@dataclass(frozen=True)
class BlockBootstrapSettings:
    """Frozen active-calendar cluster-bootstrap settings."""

    random_seed: int = DEFAULT_BLOCK_BOOTSTRAP_SEED
    bootstrap_samples: int = 10_000
    confidence_level: float = 0.95
    block_units: tuple[str, ...] = ("day", "week")
    minimum_meaningful_stress_net_margin_pips: float = 0.5

    def __post_init__(self) -> None:
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
            or self.random_seed < 0
        ):
            raise ValueError("random_seed must be a nonnegative integer")
        if self.bootstrap_samples <= 0:
            raise ValueError("bootstrap_samples must be positive")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")
        if (
            not self.block_units
            or len(set(self.block_units)) != len(self.block_units)
            or set(self.block_units).difference(("day", "week"))
        ):
            raise ValueError("block_units must be unique day/week values")
        if self.minimum_meaningful_stress_net_margin_pips <= 0:
            raise ValueError("minimum meaningful margin must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "random_seed": self.random_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "confidence_level": self.confidence_level,
            "block_units": list(self.block_units),
            "minimum_meaningful_stress_net_margin_pips": (
                self.minimum_meaningful_stress_net_margin_pips
            ),
            "effective_sample_formula": (
                "ceil(((1.96 + 0.84) * sample_stdev_net_pips / "
                "minimum_margin_pips) ** 2)"
            ),
        }


def block_bootstrap_report(
    trades: Sequence[BacktestTrade],
    *,
    symbol: SymbolRiskSpec,
    period_start: datetime = DEVELOPMENT_START,
    period_end: datetime = DEVELOPMENT_END,
    settings: BlockBootstrapSettings | None = None,
) -> dict[str, object]:
    """Resample complete active UTC-day and ISO-week trade clusters."""

    frozen = settings or BlockBootstrapSettings()
    start, end = assert_development_period(period_start, period_end)
    ordered = tuple(
        sorted(trades, key=lambda trade: (trade.entry_time, trade.exit_time))
    )
    _validate_trades(ordered, start, end)
    gross, net = _trade_pips(ordered, symbol)
    stdev = float(np.std(net, ddof=1)) if len(net) > 1 else None
    required = _required_effective_sample(stdev, frozen)
    units: dict[str, object] = {}
    for unit_number, unit in enumerate(frozen.block_units):
        blocks = _blocks(ordered, unit)
        rng = np.random.Generator(
            np.random.PCG64(
                np.random.SeedSequence((frozen.random_seed, unit_number))
            )
        )
        gross_means, net_means, drawdowns, counts = _bootstrap(
            gross, net, blocks, frozen.bootstrap_samples, rng
        )
        standard_error = (
            float(net_means.std(ddof=1)) if len(net_means) > 1 else None
        )
        effective = _effective_sample(stdev, standard_error, len(ordered))
        units[unit] = {
            "active_block_count": len(blocks),
            "trade_count": len(ordered),
            "replicate_trade_count_minimum": (
                int(counts.min()) if len(counts) else 0
            ),
            "replicate_trade_count_maximum": (
                int(counts.max()) if len(counts) else 0
            ),
            "gross_expectancy_pips": _interval(
                gross, gross_means, frozen.confidence_level
            ),
            "net_expectancy_pips": _interval(
                net, net_means, frozen.confidence_level
            ),
            "maximum_drawdown_pips": _distribution(drawdowns),
            "net_expectancy_bootstrap_standard_error_pips": standard_error,
            "implied_effective_sample_size": effective,
            "required_effective_sample_size": required,
            "effective_sample_requirement_met": (
                effective >= required
                if effective is not None and required is not None
                else False
            ),
        }
    effective = [
        float(row["implied_effective_sample_size"])
        for row in units.values()
        if isinstance(row, Mapping)
        and row.get("implied_effective_sample_size") is not None
    ]
    return {
        "methodology": {
            "bootstrap_method": (
                "non-overlapping active-calendar-block resampling"
            ),
            "calendar_attribution": "UTC trade entry time",
            "within_block_order_preserved": True,
            "empty_calendar_blocks_resampled": False,
            "estimand": "mean pips per completed signal",
            "settings": frozen.as_dict(),
        },
        "sample": {
            "trade_count": len(ordered),
            "sample_stdev_net_pips": stdev,
            "required_effective_sample_size": required,
        },
        "by_block_unit": units,
        "conservative_effective_sample_size": (
            min(effective) if effective else None
        ),
        "all_block_units_meet_effective_sample_requirement": bool(units)
        and all(
            bool(row["effective_sample_requirement_met"])
            for row in units.values()
            if isinstance(row, Mapping)
        ),
    }


@dataclass(frozen=True)
class Strategy16GateMetrics:
    """Normalized runner output consumed by the frozen gate evaluator."""

    base_emitted: int
    base_accepted: int
    base_rejected: int
    stress_emitted: int
    stress_accepted: int
    stress_rejected: int
    gross_expectancy_pips: float | None
    base_net_expectancy_pips: float | None
    stress_net_expectancy_pips: float | None
    base_profit_factor: float | None
    stress_profit_factor: float | None
    median_mfe_pips: float | None
    mfe_exceedance_ratio: float | None
    median_adverse_mae_pips: float | None
    base_cost_pips: float
    stress_cost_pips: float
    base_annual_trades: tuple[int, ...]
    stress_annual_trades: tuple[int, ...]
    base_max_entries_day: int
    stress_max_entries_day: int
    median_holding_minutes: float | None
    maximum_holding_minutes: float | None
    overnight_trades: int
    minimum_stop_pips: float | None
    minimum_reward_pips: float | None
    minimum_stress_cost_adjusted_rr: float | None
    stress_positive_years: int
    stress_year_count: int
    stress_positive_active_months: int
    stress_active_months: int
    stress_strongest_year_contribution: float | None
    stress_top_decile_contribution: float | None
    base_block_bootstrap: Mapping[str, object] | None = None
    stress_block_bootstrap: Mapping[str, object] | None = None
    downside_tail_reported: bool = False
    neighborhood_passed: bool | None = None
    risk_sized_max_drawdown_percent: float | None = None
    tick_replay_passed: bool | None = None

    def __post_init__(self) -> None:
        counts = (
            self.base_emitted,
            self.base_accepted,
            self.base_rejected,
            self.stress_emitted,
            self.stress_accepted,
            self.stress_rejected,
            *self.base_annual_trades,
            *self.stress_annual_trades,
            self.base_max_entries_day,
            self.stress_max_entries_day,
            self.overnight_trades,
            self.stress_positive_years,
            self.stress_year_count,
            self.stress_positive_active_months,
            self.stress_active_months,
        )
        if any(value < 0 for value in counts):
            raise ValueError("gate counts must not be negative")
        if self.base_emitted != self.base_accepted + self.base_rejected:
            raise ValueError("base emitted must equal accepted plus rejected")
        if self.stress_emitted != self.stress_accepted + self.stress_rejected:
            raise ValueError("stress emitted must equal accepted plus rejected")
        if self.stress_positive_years > self.stress_year_count:
            raise ValueError("positive years cannot exceed year count")
        if self.stress_positive_active_months > self.stress_active_months:
            raise ValueError("positive months cannot exceed active months")


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


def strategy17_gate_report(
    metrics: Strategy16GateMetrics,
    gate: EconomicPromotionGate,
) -> dict[str, object]:
    """Apply registry-v2 thresholds without modifying them."""

    primary = _primary_rows(metrics, gate)
    primary_passed = all(row["status"] == "PASS" for row in primary)
    robustness = _robustness_rows(
        metrics, gate, eligible=primary_passed
    )
    robustness_passed = primary_passed and all(
        row["status"] == "PASS" for row in robustness
    )
    downstream = _downstream_rows(
        metrics, gate, eligible=robustness_passed
    )
    development = [*primary, *robustness, *downstream]
    failed = [row["gate_id"] for row in development if row["status"] == "FAIL"]
    pending = [
        row["gate_id"]
        for row in development
        if row["status"] == "NOT_EVALUATED"
    ]
    decision = "FAIL" if failed else ("INCOMPLETE" if pending else "PASS")
    tick_status = (
        "PASS"
        if not gate.require_tick_replay_pass
        or metrics.tick_replay_passed is True
        else "NOT_EVALUATED"
        if metrics.tick_replay_passed is None
        else "FAIL"
    )
    return {
        "gate_id": gate.gate_id,
        "frozen_gate": gate.model_dump(mode="json"),
        "development_decision": decision,
        "primary_economic_gates_passed": primary_passed,
        "robustness_eligible": primary_passed,
        "robustness_gates_passed": robustness_passed,
        "failed_gate_ids": failed,
        "not_evaluated_gate_ids": pending,
        "development_gates": development,
        "pre_demo_gate": {
            "gate_id": "tick_replay",
            "stage": "pre_demo",
            "observed": metrics.tick_replay_passed,
            "status": tick_status,
        },
        "demo_eligible": decision == "PASS" and tick_status == "PASS",
    }



def _primary_rows(
    m: Strategy16GateMetrics, g: EconomicPromotionGate
) -> list[dict[str, object]]:
    month_ratio = (
        m.stress_positive_active_months / m.stress_active_months
        if m.stress_active_months
        else None
    )
    annual = (*m.base_annual_trades, *m.stress_annual_trades)
    annual_pass = (
        len(m.base_annual_trades) == g.development_year_count
        and len(m.stress_annual_trades) == g.development_year_count
        and all(
            g.minimum_annual_signals <= value <= g.maximum_annual_signals
            for value in annual
        )
    )
    values = [
        (
            "gross_expectancy",
            m.gross_expectancy_pips,
            _ge(m.gross_expectancy_pips, g.minimum_gross_expectancy_pips),
        ),
        (
            "base_net_expectancy",
            m.base_net_expectancy_pips,
            _ge(m.base_net_expectancy_pips, g.minimum_base_net_expectancy_pips),
        ),
        (
            "stress_net_expectancy",
            m.stress_net_expectancy_pips,
            _ge(m.stress_net_expectancy_pips, g.minimum_stress_net_expectancy_pips),
        ),
        (
            "median_mfe",
            m.median_mfe_pips,
            _ge(m.median_mfe_pips, g.minimum_median_mfe_pips),
        ),
        (
            "mfe_exceedance",
            m.mfe_exceedance_ratio,
            _ge(m.mfe_exceedance_ratio, g.minimum_mfe_exceedance_ratio),
        ),
        (
            "mfe_mae_ratio",
            _ratio(m.median_mfe_pips, m.median_adverse_mae_pips),
            _ge(
                _ratio(m.median_mfe_pips, m.median_adverse_mae_pips),
                g.minimum_median_mfe_mae_ratio,
            ),
        ),
        (
            "base_cost_mfe_ratio",
            _ratio(m.base_cost_pips, m.median_mfe_pips),
            _le(
                _ratio(m.base_cost_pips, m.median_mfe_pips),
                g.maximum_base_cost_mfe_ratio,
            ),
        ),
        (
            "stress_cost_mfe_ratio",
            _ratio(m.stress_cost_pips, m.median_mfe_pips),
            _le(
                _ratio(m.stress_cost_pips, m.median_mfe_pips),
                g.maximum_stress_cost_mfe_ratio,
            ),
        ),
        (
            "annual_signal_frequency",
            {
                "base": list(m.base_annual_trades),
                "stress": list(m.stress_annual_trades),
            },
            annual_pass,
        ),
        (
            "maximum_entries_per_day",
            {
                "base": m.base_max_entries_day,
                "stress": m.stress_max_entries_day,
            },
            max(m.base_max_entries_day, m.stress_max_entries_day)
            <= g.maximum_entries_per_day,
        ),
        (
            "median_holding",
            m.median_holding_minutes,
            m.median_holding_minutes is not None
            and g.minimum_median_holding_minutes
            <= m.median_holding_minutes
            <= g.maximum_median_holding_minutes,
        ),
        (
            "hard_holding_exit",
            m.maximum_holding_minutes,
            _le(m.maximum_holding_minutes, g.hard_maximum_holding_minutes),
        ),
        (
            "overnight_positions",
            m.overnight_trades,
            g.allow_overnight_positions or m.overnight_trades == 0,
        ),
        (
            "minimum_stop_pips",
            m.minimum_stop_pips,
            _ge(m.minimum_stop_pips, g.minimum_stop_pips),
        ),
        (
            "minimum_stop_cost_multiple",
            _ratio(m.minimum_stop_pips, m.stress_cost_pips),
            _ge(
                _ratio(m.minimum_stop_pips, m.stress_cost_pips),
                g.minimum_stop_stress_cost_multiple,
            ),
        ),
        (
            "minimum_reward_cost_multiple",
            _ratio(m.minimum_reward_pips, m.stress_cost_pips),
            _ge(
                _ratio(m.minimum_reward_pips, m.stress_cost_pips),
                g.minimum_reward_stress_cost_multiple,
            ),
        ),
        (
            "cost_adjusted_reward_risk",
            m.minimum_stress_cost_adjusted_rr,
            _ge(
                m.minimum_stress_cost_adjusted_rr,
                g.minimum_cost_adjusted_reward_risk,
            ),
        ),
        (
            "base_profit_factor",
            m.base_profit_factor,
            _ge(m.base_profit_factor, g.minimum_base_profit_factor),
        ),
        (
            "stress_profit_factor",
            m.stress_profit_factor,
            _ge(m.stress_profit_factor, g.minimum_stress_profit_factor),
        ),
        (
            "positive_years",
            f"{m.stress_positive_years}/{m.stress_year_count}",
            m.stress_year_count == g.development_year_count
            and m.stress_positive_years >= g.minimum_positive_years,
        ),
        (
            "positive_active_months",
            month_ratio,
            _ge(month_ratio, g.minimum_positive_active_month_ratio),
        ),
    ]
    return [_row(name, observed, passed) for name, observed, passed in values]


def _robustness_rows(
    m: Strategy16GateMetrics,
    g: EconomicPromotionGate,
    *,
    eligible: bool,
) -> list[dict[str, object]]:
    names = (
        "gross_block_bootstrap",
        "stress_net_block_bootstrap",
        "effective_sample_size",
        "downside_tail",
        "strongest_year_concentration",
        "top_decile_concentration",
    )
    if not eligible:
        return [_not_run(name, "primary gates failed") for name in names]
    base = _bootstrap_units(m.base_block_bootstrap)
    stress = _bootstrap_units(m.stress_block_bootstrap)
    required = set(g.bootstrap_units)
    gross = _unit_values(base, "gross_expectancy_pips", "lower")
    net = _unit_values(stress, "net_expectancy_pips", "lower")
    effective = {
        unit: {
            "observed": row.get("implied_effective_sample_size"),
            "required": row.get("required_effective_sample_size"),
        }
        for unit, row in stress.items()
    }
    values = [
        (
            "gross_block_bootstrap",
            gross,
            (not g.require_block_bootstrap_pass)
            or (
                set(gross) == required
                and all(
                    value > g.minimum_gross_block_bootstrap_lower_bound_pips
                    for value in gross.values()
                )
            ),
        ),
        (
            "stress_net_block_bootstrap",
            net,
            (not g.require_block_bootstrap_pass)
            or (
                set(net) == required
                and all(value > 0 for value in net.values())
            ),
        ),
        (
            "effective_sample_size",
            effective,
            (not g.require_effective_sample_size_pass)
            or (
                set(stress) == required
                and all(
                    bool(row.get("effective_sample_requirement_met"))
                    for row in stress.values()
                )
            ),
        ),
        (
            "downside_tail",
            m.downside_tail_reported,
            (not g.require_downside_tail_diagnostic)
            or m.downside_tail_reported,
        ),
        (
            "strongest_year_concentration",
            m.stress_strongest_year_contribution,
            _le(
                m.stress_strongest_year_contribution,
                g.maximum_strongest_year_profit_contribution,
            ),
        ),
        (
            "top_decile_concentration",
            m.stress_top_decile_contribution,
            _le(
                m.stress_top_decile_contribution,
                g.maximum_top_decile_trade_profit_contribution,
            ),
        ),
    ]
    return [_row(name, observed, passed) for name, observed, passed in values]


def _downstream_rows(
    m: Strategy16GateMetrics,
    g: EconomicPromotionGate,
    *,
    eligible: bool,
) -> list[dict[str, object]]:
    if not eligible:
        return [
            _not_run("parameter_neighborhood", "robustness gates failed"),
            _not_run("risk_sized_drawdown", "robustness gates failed"),
        ]
    rows: list[dict[str, object]] = []
    if g.require_parameter_neighborhood_pass and m.neighborhood_passed is None:
        rows.append(_not_run("parameter_neighborhood", "conditional test not run"))
    else:
        rows.append(
            _row(
                "parameter_neighborhood",
                m.neighborhood_passed,
                (not g.require_parameter_neighborhood_pass)
                or m.neighborhood_passed is True,
            )
        )
    if g.require_risk_sized_portfolio_pass and m.risk_sized_max_drawdown_percent is None:
        rows.append(_not_run("risk_sized_drawdown", "conditional test not run"))
    else:
        rows.append(
            _row(
                "risk_sized_drawdown",
                m.risk_sized_max_drawdown_percent,
                (not g.require_risk_sized_portfolio_pass)
                or _le(m.risk_sized_max_drawdown_percent, g.maximum_drawdown_percent),
            )
        )
    return rows


def _trade_pips(    trades: Sequence[BacktestTrade], symbol: SymbolRiskSpec
) -> tuple[np.ndarray, np.ndarray]:
    if any(trade.volume_lots <= 0 for trade in trades):
        raise ValueError("bootstrap trades must have positive volume")
    pip_value = 0.0001 / symbol.tick_size * symbol.tick_value
    gross = np.asarray(
        [
            trade.gross_pnl / (pip_value * trade.volume_lots)
            for trade in trades
        ],
        dtype=np.float64,
    )
    net = np.asarray(
        [
            trade.net_pnl / (pip_value * trade.volume_lots)
            for trade in trades
        ],
        dtype=np.float64,
    )
    if not np.isfinite(gross).all() or not np.isfinite(net).all():
        raise ValueError("bootstrap trade economics must be finite")
    return gross, net


def _blocks(
    trades: Sequence[BacktestTrade], unit: str
) -> list[np.ndarray]:
    grouped: dict[date, list[int]] = {}
    for index, trade in enumerate(trades):
        entry = trade.entry_time.astimezone(UTC)
        key = (
            entry.date()
            if unit == "day"
            else entry.date() - timedelta(days=entry.weekday())
        )
        grouped.setdefault(key, []).append(index)
    return [
        np.asarray(grouped[key], dtype=np.int64) for key in sorted(grouped)
    ]


def _bootstrap(
    gross: np.ndarray,
    net: np.ndarray,
    blocks: Sequence[np.ndarray],
    samples: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not blocks:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty, empty, np.empty(0, dtype=np.int64)
    gross_means = np.empty(samples)
    net_means = np.empty(samples)
    drawdowns = np.empty(samples)
    counts = np.empty(samples, dtype=np.int64)
    for sample in range(samples):
        chosen = rng.integers(0, len(blocks), size=len(blocks))
        indices = np.concatenate([blocks[int(index)] for index in chosen])
        counts[sample] = len(indices)
        gross_means[sample] = gross[indices].mean()
        net_means[sample] = net[indices].mean()
        drawdowns[sample] = _maximum_drawdown(net[indices])
    return gross_means, net_means, drawdowns, counts


def _interval(
    values: np.ndarray, means: np.ndarray, confidence: float
) -> dict[str, object]:
    if not len(values):
        return {
            "point_estimate": None,
            "lower": None,
            "upper": None,
            "bootstrap_sample_count": 0,
        }
    alpha = 1 - confidence
    lower, upper = np.quantile(means, (alpha / 2, 1 - alpha / 2))
    return {
        "point_estimate": float(values.mean()),
        "confidence_level": confidence,
        "lower": float(lower),
        "upper": float(upper),
        "bootstrap_mean": float(means.mean()),
        "bootstrap_standard_error": float(means.std(ddof=1)),
        "bootstrap_sample_count": len(means),
    }


def _distribution(values: np.ndarray) -> dict[str, object]:
    return {
        "sample_count": len(values),
        "median": float(np.quantile(values, 0.5)) if len(values) else None,
        "p95": float(np.quantile(values, 0.95)) if len(values) else None,
        "maximum": float(values.max()) if len(values) else None,
    }


def _required_effective_sample(
    stdev: float | None, settings: BlockBootstrapSettings
) -> int | None:
    if stdev is None:
        return None
    return ceil(
        (
            2.8
            * stdev
            / settings.minimum_meaningful_stress_net_margin_pips
        )
        ** 2
    )


def _effective_sample(
    stdev: float | None, standard_error: float | None, count: int
) -> float | None:
    if stdev is None or standard_error is None or count <= 0:
        return None
    if standard_error == 0:
        return float(count)
    return max(
        1.0,
        min(float(count), (stdev / standard_error) ** 2),
    )


def _maximum_drawdown(values: np.ndarray) -> float:
    if not len(values):
        return 0.0
    cumulative = np.cumsum(values)
    peaks = np.maximum.accumulate(cumulative)
    np.maximum(peaks, 0.0, out=peaks)
    return float((peaks - cumulative).max())


def _validate_trades(
    trades: Sequence[BacktestTrade], start: datetime, end: datetime
) -> None:
    for trade in trades:
        if trade.entry_time.tzinfo is None or trade.exit_time.tzinfo is None:
            raise ValueError("bootstrap timestamps must be timezone-aware")
        entry = trade.entry_time.astimezone(UTC)
        exit_time = trade.exit_time.astimezone(UTC)
        if not (start <= entry < end) or not (start <= exit_time < end):
            raise SplitIsolationError("bootstrap trade lies outside development")


def _bootstrap_units(
    report: Mapping[str, object] | None,
) -> dict[str, Mapping[str, Any]]:
    raw = report.get("by_block_unit") if isinstance(report, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if key in ("day", "week") and isinstance(value, Mapping)
    }


def _unit_values(
    units: Mapping[str, Mapping[str, Any]], section: str, field: str
) -> dict[str, float]:
    output: dict[str, float] = {}
    for unit in ("day", "week"):
        nested = units.get(unit, {}).get(section)
        value = nested.get(field) if isinstance(nested, Mapping) else None
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        ):
            output[unit] = float(value)
    return output


def _row(
    gate_id: str, observed: object, passed: bool
) -> dict[str, object]:
    return {
        "gate_id": gate_id,
        "stage": "development",
        "observed": observed,
        "status": GateStatus.PASS.value if passed else GateStatus.FAIL.value,
    }


def _not_run(gate_id: str, reason: str) -> dict[str, object]:
    return {
        "gate_id": gate_id,
        "stage": "development",
        "observed": None,
        "status": GateStatus.NOT_EVALUATED.value,
        "reason": reason,
    }


def _ratio(
    numerator: float | None, denominator: float | None
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _ge(value: float | str | None, threshold: float) -> bool:
    if value == "infinity":
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= threshold


def _le(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold

