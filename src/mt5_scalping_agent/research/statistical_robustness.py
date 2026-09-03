"""Deterministic statistical diagnostics for completed backtest trades."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil, fsum, isclose, sqrt

import numpy as np

from mt5_scalping_agent.backtesting import BacktestTrade


DEFAULT_BOOTSTRAP_SEED = 20_260_824


@dataclass(frozen=True)
class StatisticalRobustnessSettings:
    """Frozen evaluation settings; none of these values affect strategy rules."""

    random_seed: int = DEFAULT_BOOTSTRAP_SEED
    bootstrap_samples: int = 1_000
    confidence_level: float = 0.95
    distribution_quantiles: tuple[float, ...] = (0.05, 0.25, 0.50, 0.75, 0.95)
    top_trade_fractions: tuple[float, ...] = (0.01, 0.05, 0.10)
    downside_tail_probability: float = 0.05

    def __post_init__(self) -> None:
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int) or self.random_seed < 0:
            raise ValueError("random_seed must be a nonnegative integer")
        if self.bootstrap_samples <= 0:
            raise ValueError("bootstrap_samples must be positive")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")
        _validate_probability_sequence(
            self.distribution_quantiles,
            "distribution_quantiles",
            strictly_increasing=True,
        )
        _validate_probability_sequence(
            self.top_trade_fractions,
            "top_trade_fractions",
            strictly_increasing=True,
        )
        if not 0 < self.downside_tail_probability <= 0.5:
            raise ValueError("downside_tail_probability must be in (0, 0.5]")

    def as_dict(self) -> dict[str, object]:
        return {
            "random_seed": self.random_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "confidence_level": self.confidence_level,
            "distribution_quantiles": list(self.distribution_quantiles),
            "top_trade_fractions": list(self.top_trade_fractions),
            "downside_tail_probability": self.downside_tail_probability,
        }


def statistical_robustness_report(
    trades: Sequence[BacktestTrade],
    *,
    period_start: datetime,
    period_end: datetime,
    settings: StatisticalRobustnessSettings | None = None,
) -> dict[str, object]:
    """Evaluate uncertainty, stability, concentration, and downside behaviour.

    The bootstrap is an IID completed-trade bootstrap. It is deterministic for
    the frozen seed and estimates sampling uncertainty only; it does not retain
    serial dependence and is not used to search strategy parameters.
    """
    settings = settings or StatisticalRobustnessSettings()
    start, end = _normalized_period(period_start, period_end)
    ordered = tuple(sorted(trades, key=lambda trade: (trade.exit_time, trade.entry_time)))
    _validate_trade_period(ordered, start, end)

    gross = np.fromiter((trade.gross_pnl for trade in ordered), dtype=np.float64)
    net = np.fromiter((trade.net_pnl for trade in ordered), dtype=np.float64)
    costs = np.fromiter(
        (float(trade.total_transaction_cost or 0.0) for trade in ordered),
        dtype=np.float64,
    )
    if not (np.isfinite(gross).all() and np.isfinite(net).all() and np.isfinite(costs).all()):
        raise ValueError("statistical trade economics must be finite")
    bootstrap = _bootstrap_distributions(gross, net, settings)
    yearly = _calendar_consistency(ordered, start, end, "year")
    monthly = _calendar_consistency(ordered, start, end, "month")

    gross_total = fsum(float(value) for value in gross)
    cost_total = fsum(float(value) for value in costs)
    net_total = fsum(float(value) for value in net)
    accounting_residual = gross_total - cost_total - net_total
    return {
        "methodology": {
            "purpose": "diagnostic evaluation only; no strategy parameter search",
            "bootstrap_method": "IID completed-trade resampling with replacement",
            "bootstrap_rng": "NumPy PCG64",
            "confidence_interval_method": "percentile bootstrap with linear quantiles",
            "serial_dependence_preserved": False,
            "drawdown_bootstrap_order": "resampled trade sequence",
            "calendar_attribution": "trade entry time",
            "settings": settings.as_dict(),
        },
        "sample": {
            "trade_count": len(ordered),
            "gross_pnl": gross_total,
            "total_transaction_cost": cost_total,
            "net_pnl": net_total,
            "accounting_identity_residual": accounting_residual,
            "accounting_identity_holds": isclose(
                gross_total - cost_total,
                net_total,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ),
        },
        "bootstrap": {
            "gross_expectancy_per_trade": _expectancy_interval(
                gross, bootstrap["gross_means"], settings
            ),
            "net_expectancy_per_trade": _expectancy_interval(
                net, bootstrap["net_means"], settings
            ),
            "profit_factor": _profit_factor_distribution(
                net,
                bootstrap["profit_factors"],
                int(bootstrap["infinite_profit_factors"]),
                int(bootstrap["undefined_profit_factors"]),
                settings,
            ),
            "maximum_drawdown": {
                "point_estimate": _maximum_drawdown(net),
                **_distribution_summary(
                    bootstrap["max_drawdowns"], settings.distribution_quantiles
                ),
            },
        },
        "consistency": {
            "yearly": yearly,
            "monthly": monthly,
        },
        "concentration": {
            "top_trade_basis": (
                "share of all completed trades, ranked separately by positive gross or "
                "positive net PnL; contribution denominator is the matching positive-trade profit pool"
            ),
            "gross_by_top_trades": _top_trade_concentration(
                gross, settings.top_trade_fractions
            ),
            "net_by_top_trades": _top_trade_concentration(
                net, settings.top_trade_fractions
            ),
            "strongest_period_basis": (
                "strongest aggregate calendar period divided by the sum of positive "
                "aggregate periods for the matching PnL measure"
            ),
            "strongest_year": {
                "gross": _strongest_period_concentration(yearly["periods"], "gross_pnl"),
                "net": _strongest_period_concentration(yearly["periods"], "net_pnl"),
            },
            "strongest_month": {
                "gross": _strongest_period_concentration(monthly["periods"], "gross_pnl"),
                "net": _strongest_period_concentration(monthly["periods"], "net_pnl"),
            },
        },
        "downside_tail": _downside_tail(net, settings.downside_tail_probability),
    }


def _bootstrap_distributions(
    gross: np.ndarray,
    net: np.ndarray,
    settings: StatisticalRobustnessSettings,
) -> dict[str, object]:
    count = len(net)
    if count == 0:
        empty = np.empty(0, dtype=np.float64)
        return {
            "gross_means": empty,
            "net_means": empty,
            "profit_factors": empty,
            "max_drawdowns": empty,
            "infinite_profit_factors": 0,
            "undefined_profit_factors": 0,
        }

    samples = settings.bootstrap_samples
    gross_means = np.empty(samples, dtype=np.float64)
    net_means = np.empty(samples, dtype=np.float64)
    max_drawdowns = np.empty(samples, dtype=np.float64)
    finite_profit_factors: list[np.ndarray] = []
    infinite_profit_factors = 0
    undefined_profit_factors = 0
    generator = np.random.Generator(np.random.PCG64(settings.random_seed))

    # Bound temporary arrays while retaining exact n-trade bootstrap samples.
    maximum_chunk_elements = 1_000_000
    chunk_size = max(1, min(samples, maximum_chunk_elements // count))
    cursor = 0
    while cursor < samples:
        chunk = min(chunk_size, samples - cursor)
        indices = generator.integers(0, count, size=(chunk, count), dtype=np.int64)
        sampled_gross = gross[indices]
        sampled_net = net[indices]
        gross_means[cursor : cursor + chunk] = sampled_gross.mean(axis=1)
        net_means[cursor : cursor + chunk] = sampled_net.mean(axis=1)

        positive = np.where(sampled_net > 0, sampled_net, 0.0).sum(axis=1)
        negative = -np.where(sampled_net < 0, sampled_net, 0.0).sum(axis=1)
        finite = negative > 0
        if finite.any():
            finite_profit_factors.append(positive[finite] / negative[finite])
        infinite_profit_factors += int(((negative == 0) & (positive > 0)).sum())
        undefined_profit_factors += int(((negative == 0) & (positive == 0)).sum())

        cumulative = np.cumsum(sampled_net, axis=1)
        peaks = np.maximum.accumulate(cumulative, axis=1)
        np.maximum(peaks, 0.0, out=peaks)
        peaks -= cumulative
        max_drawdowns[cursor : cursor + chunk] = peaks.max(axis=1)
        cursor += chunk

    profit_factors = (
        np.concatenate(finite_profit_factors)
        if finite_profit_factors
        else np.empty(0, dtype=np.float64)
    )
    return {
        "gross_means": gross_means,
        "net_means": net_means,
        "profit_factors": profit_factors,
        "max_drawdowns": max_drawdowns,
        "infinite_profit_factors": infinite_profit_factors,
        "undefined_profit_factors": undefined_profit_factors,
    }


def _expectancy_interval(
    values: np.ndarray,
    bootstrap_means: object,
    settings: StatisticalRobustnessSettings,
) -> dict[str, object]:
    means = np.asarray(bootstrap_means, dtype=np.float64)
    if len(values) == 0:
        return {
            "point_estimate": None,
            "confidence_level": settings.confidence_level,
            "lower": None,
            "upper": None,
            "bootstrap_mean": None,
            "bootstrap_standard_error": None,
            "bootstrap_sample_count": 0,
        }
    alpha = 1.0 - settings.confidence_level
    lower, upper = np.quantile(means, (alpha / 2.0, 1.0 - alpha / 2.0))
    return {
        "point_estimate": float(values.mean()),
        "confidence_level": settings.confidence_level,
        "lower": float(lower),
        "upper": float(upper),
        "bootstrap_mean": float(means.mean()),
        "bootstrap_standard_error": (
            float(means.std(ddof=1)) if len(means) > 1 else 0.0
        ),
        "bootstrap_sample_count": len(means),
    }


def _profit_factor_distribution(
    net: np.ndarray,
    finite_bootstrap: object,
    infinite_count: int,
    undefined_count: int,
    settings: StatisticalRobustnessSettings,
) -> dict[str, object]:
    wins = float(net[net > 0].sum())
    losses = float(-net[net < 0].sum())
    if losses > 0:
        point: float | str | None = wins / losses
    elif wins > 0:
        point = "infinity"
    else:
        point = None
    return {
        "point_estimate": point,
        "finite_distribution": _distribution_summary(
            np.asarray(finite_bootstrap, dtype=np.float64),
            settings.distribution_quantiles,
        ),
        "finite_sample_count": len(np.asarray(finite_bootstrap)),
        "infinite_sample_count": infinite_count,
        "undefined_sample_count": undefined_count,
        "requested_bootstrap_sample_count": (
            settings.bootstrap_samples if len(net) else 0
        ),
    }


def _distribution_summary(
    values: np.ndarray, quantiles: Sequence[float]
) -> dict[str, object]:
    finite = np.asarray(values, dtype=np.float64)
    if len(finite) == 0:
        return {
            "sample_count": 0,
            "mean": None,
            "minimum": None,
            "maximum": None,
            "quantiles": {_probability_key(q): None for q in quantiles},
        }
    values_at_quantiles = np.quantile(finite, quantiles)
    return {
        "sample_count": len(finite),
        "mean": float(finite.mean()),
        "minimum": float(finite.min()),
        "maximum": float(finite.max()),
        "quantiles": {
            _probability_key(probability): float(value)
            for probability, value in zip(quantiles, values_at_quantiles, strict=True)
        },
    }


def _calendar_consistency(
    trades: Sequence[BacktestTrade],
    start: datetime,
    end: datetime,
    frequency: str,
) -> dict[str, object]:
    labels = _calendar_labels(start, end, frequency)
    grouped: dict[str, list[BacktestTrade]] = {label: [] for label in labels}
    for trade in trades:
        entry = _as_utc(trade.entry_time)
        label = (
            f"{entry.year:04d}"
            if frequency == "year"
            else f"{entry.year:04d}-{entry.month:02d}"
        )
        grouped[label].append(trade)

    periods = []
    for label in labels:
        period_trades = grouped[label]
        gross = fsum(trade.gross_pnl for trade in period_trades)
        costs = fsum(float(trade.total_transaction_cost or 0.0) for trade in period_trades)
        net = fsum(trade.net_pnl for trade in period_trades)
        periods.append(
            {
                "period": label,
                "trade_count": len(period_trades),
                "gross_pnl": gross,
                "total_transaction_cost": costs,
                "net_pnl": net,
                "gross_expectancy_per_trade": (
                    gross / len(period_trades) if period_trades else None
                ),
                "net_expectancy_per_trade": (
                    net / len(period_trades) if period_trades else None
                ),
            }
        )
    active = [row for row in periods if row["trade_count"]]
    positive = [row for row in periods if float(row["net_pnl"]) > 0]
    negative = [row for row in periods if float(row["net_pnl"]) < 0]
    positive_active = [row for row in active if float(row["net_pnl"]) > 0]
    return {
        "period_count": len(periods),
        "active_period_count": len(active),
        "positive_period_count": len(positive),
        "negative_period_count": len(negative),
        "flat_period_count": len(periods) - len(positive) - len(negative),
        "positive_period_fraction": len(positive) / len(periods) if periods else None,
        "positive_active_period_fraction": (
            len(positive_active) / len(active) if active else None
        ),
        "strongest_period": _period_extreme(active, strongest=True),
        "weakest_period": _period_extreme(active, strongest=False),
        "periods": periods,
    }


def _top_trade_concentration(
    values: np.ndarray, fractions: Sequence[float]
) -> list[dict[str, object]]:
    count = len(values)
    positive_pool = float(values[values > 0].sum())
    descending = np.sort(values)[::-1]
    rows = []
    for fraction in fractions:
        top_count = min(count, max(1, ceil(count * fraction))) if count else 0
        contribution = (
            float(np.maximum(descending[:top_count], 0.0).sum()) if top_count else 0.0
        )
        ratio = contribution / positive_pool if positive_pool > 0 else None
        rows.append(
            {
                "top_trade_fraction": fraction,
                "top_trade_count": top_count,
                "positive_profit_pool": positive_pool,
                "top_trade_positive_profit": contribution,
                "contribution_fraction": ratio,
                "contribution_percent": ratio * 100.0 if ratio is not None else None,
            }
        )
    return rows


def _strongest_period_concentration(
    periods: object, pnl_field: str
) -> dict[str, object]:
    rows = (
        [row for row in periods if int(row.get("trade_count", 0)) > 0]
        if isinstance(periods, list)
        else []
    )
    if not rows:
        return {
            "period": None,
            "period_pnl": None,
            "positive_period_profit_pool": 0.0,
            "contribution_fraction": None,
            "contribution_percent": None,
        }
    strongest = max(rows, key=lambda row: float(row[pnl_field]))
    pool = fsum(max(0.0, float(row[pnl_field])) for row in rows)
    pnl = float(strongest[pnl_field])
    contribution = max(0.0, pnl) / pool if pool > 0 else None
    return {
        "period": strongest["period"],
        "period_pnl": pnl,
        "positive_period_profit_pool": pool,
        "contribution_fraction": contribution,
        "contribution_percent": contribution * 100.0 if contribution is not None else None,
    }


def _downside_tail(net: np.ndarray, probability: float) -> dict[str, object]:
    if len(net) == 0:
        return {
            "tail_probability": probability,
            "pnl_quantile": None,
            "expected_shortfall": None,
            "tail_observation_count": 0,
            "worst_trade_net_pnl": None,
            "loss_trade_count": 0,
            "loss_trade_fraction": None,
            "average_loss": None,
            "downside_deviation_from_zero": None,
            "tail_share_of_total_loss": None,
            "maximum_consecutive_losses": 0,
        }
    threshold = float(np.quantile(net, probability))
    tail = net[net <= threshold]
    losses = net[net < 0]
    tail_losses = -tail[tail < 0].sum()
    total_loss = -losses.sum()
    downside = np.minimum(net, 0.0)
    return {
        "tail_probability": probability,
        "pnl_quantile": threshold,
        "expected_shortfall": float(tail.mean()),
        "tail_observation_count": len(tail),
        "worst_trade_net_pnl": float(net.min()),
        "loss_trade_count": len(losses),
        "loss_trade_fraction": len(losses) / len(net),
        "average_loss": float(losses.mean()) if len(losses) else None,
        "downside_deviation_from_zero": float(sqrt(float(np.mean(downside**2)))),
        "tail_share_of_total_loss": (
            float(tail_losses / total_loss) if total_loss > 0 else None
        ),
        "maximum_consecutive_losses": _maximum_consecutive_losses(net),
    }


def _maximum_drawdown(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    cumulative = np.cumsum(values)
    peaks = np.maximum.accumulate(cumulative)
    peaks = np.maximum(peaks, 0.0)
    return float((peaks - cumulative).max())


def _maximum_consecutive_losses(values: np.ndarray) -> int:
    maximum = current = 0
    for value in values:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _period_extreme(
    periods: Sequence[dict[str, object]], *, strongest: bool
) -> dict[str, object] | None:
    if not periods:
        return None
    key = lambda row: float(row["net_pnl"])
    return dict(max(periods, key=key) if strongest else min(periods, key=key))


def _calendar_labels(start: datetime, end: datetime, frequency: str) -> list[str]:
    final = end - timedelta(microseconds=1)
    year, month = start.year, start.month
    months: list[tuple[int, int]] = []
    while (year, month) <= (final.year, final.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    if frequency == "month":
        return [f"{year:04d}-{month:02d}" for year, month in months]
    if frequency == "year":
        return list(dict.fromkeys(f"{year:04d}" for year, _ in months))
    raise ValueError("frequency must be 'year' or 'month'")


def _normalized_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("statistical period boundaries must be timezone-aware")
    normalized_start, normalized_end = start.astimezone(UTC), end.astimezone(UTC)
    if normalized_start >= normalized_end:
        raise ValueError("statistical period start must precede end")
    return normalized_start, normalized_end


def _validate_trade_period(
    trades: Sequence[BacktestTrade], start: datetime, end: datetime
) -> None:
    for trade in trades:
        entry, exit_time = _as_utc(trade.entry_time), _as_utc(trade.exit_time)
        if not (start <= entry < end) or not (start <= exit_time < end):
            raise ValueError("statistical trade lies outside the requested evaluation period")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("trade timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _validate_probability_sequence(
    values: Sequence[float], name: str, *, strictly_increasing: bool
) -> None:
    if not values or any(not 0 < value <= 1 for value in values):
        raise ValueError(f"{name} must contain probabilities in (0, 1]")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
    if strictly_increasing and tuple(values) != tuple(sorted(values)):
        raise ValueError(f"{name} must be strictly increasing")


def _probability_key(probability: float) -> str:
    return f"p{probability * 100:g}"
