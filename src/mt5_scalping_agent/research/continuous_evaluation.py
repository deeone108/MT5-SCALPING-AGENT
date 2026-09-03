"""Continuous development-period diagnostics without changing strategy rules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import fsum
from typing import Any

import pandas as pd

from mt5_scalping_agent.backtesting import (
    BacktestResult,
    BacktestTrade,
    backtest_summary,
    trade_record,
)
from mt5_scalping_agent.data.sessions import session_name
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research.statistical_robustness import (
    StatisticalRobustnessSettings,
    statistical_robustness_report,
)


DEVELOPMENT_START = datetime(2019, 1, 1, tzinfo=UTC)
DEVELOPMENT_END = datetime(2024, 1, 1, tzinfo=UTC)
POST_SELECTION_START = DEVELOPMENT_END


class SplitIsolationError(ValueError):
    """Raised when post-selection observations enter a development evaluation."""


@dataclass(frozen=True)
class VolatilityRegimeSettings:
    """Frozen, diagnostic-only ATR regime definition.

    At a candle's opening timestamp the diagnostic uses ATR through the prior
    completed candle and compares it with a trailing median of similarly lagged
    ATR values. It does not participate in signal generation.
    """

    atr_period_bars: int = 14
    baseline_window_bars: int = 1_440
    baseline_minimum_bars: int = 60
    low_ratio_maximum: float = 0.75
    high_ratio_minimum: float = 1.50

    def __post_init__(self) -> None:
        if self.atr_period_bars <= 0:
            raise ValueError("atr_period_bars must be positive")
        if self.baseline_window_bars <= 0:
            raise ValueError("baseline_window_bars must be positive")
        if not 0 < self.baseline_minimum_bars <= self.baseline_window_bars:
            raise ValueError(
                "baseline_minimum_bars must be positive and no greater than baseline_window_bars"
            )
        if self.low_ratio_maximum <= 0:
            raise ValueError("low_ratio_maximum must be positive")
        if self.high_ratio_minimum <= self.low_ratio_maximum:
            raise ValueError("high_ratio_minimum must exceed low_ratio_maximum")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": "lagged_atr_relative_to_trailing_median",
            "atr_period_bars": self.atr_period_bars,
            "baseline_window_bars": self.baseline_window_bars,
            "baseline_minimum_bars": self.baseline_minimum_bars,
            "low_ratio_maximum": self.low_ratio_maximum,
            "high_ratio_minimum": self.high_ratio_minimum,
            "signal_rule": False,
            "observation_timing": "only candles completed before trade entry",
        }


def assert_development_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Normalize and enforce a range contained entirely in 2019-2023."""
    if start.tzinfo is None or end.tzinfo is None:
        raise SplitIsolationError("development boundaries must be timezone-aware")
    normalized_start, normalized_end = start.astimezone(UTC), end.astimezone(UTC)
    if normalized_start >= normalized_end:
        raise SplitIsolationError("development start must precede end")
    if normalized_start < DEVELOPMENT_START or normalized_end > DEVELOPMENT_END:
        raise SplitIsolationError(
            "continuous development evaluation is isolated to [2019-01-01, 2024-01-01); "
            "2024-2026 is post-selection robustness evidence"
        )
    return normalized_start, normalized_end


def causal_volatility_regimes(
    candles: pd.DataFrame,
    settings: VolatilityRegimeSettings = VolatilityRegimeSettings(),
) -> pd.DataFrame:
    """Return causal volatility labels available at each M1 candle open."""
    data = validate_ohlcv(candles)
    _assert_candles_are_development_only(data)

    previous_close = data["close"].shift(1)
    true_range = pd.concat(
        (
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(
        settings.atr_period_bars,
        min_periods=settings.atr_period_bars,
    ).mean()

    # A trade entering at row t can only use diagnostics through row t-1.
    atr_at_entry = atr.shift(1)
    baseline_at_entry = atr_at_entry.rolling(
        settings.baseline_window_bars,
        min_periods=settings.baseline_minimum_bars,
    ).median()
    ratio = atr_at_entry / baseline_at_entry.where(baseline_at_entry > 0)
    labels = pd.Series("unavailable", index=data.index, dtype="object")
    available = ratio.notna()
    labels.loc[available] = "normal"
    labels.loc[available & (ratio <= settings.low_ratio_maximum)] = "low"
    labels.loc[available & (ratio >= settings.high_ratio_minimum)] = "high"

    return pd.DataFrame(
        {
            "time": data["time"],
            "atr_at_entry": atr_at_entry,
            "baseline_at_entry": baseline_at_entry,
            "volatility_ratio": ratio,
            "volatility_regime": labels,
        }
    ).reset_index(drop=True)


def continuous_result_report(
    result: BacktestResult,
    candles: pd.DataFrame,
    *,
    period_start: datetime = DEVELOPMENT_START,
    period_end: datetime = DEVELOPMENT_END,
    initial_balance: float,
    symbol: str,
    volatility_settings: VolatilityRegimeSettings = VolatilityRegimeSettings(),
    statistical_settings: StatisticalRobustnessSettings = StatisticalRobustnessSettings(),
    precomputed_volatility: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Build complete and partitioned diagnostics for one continuous run.

    Calendar, direction, session, and regime attribution all use trade entry
    time. Subgroup drawdowns are reconstructed from the subgroup's ordered net
    trade results and do not imply a separately reset backtest.
    """
    start, end = assert_development_period(period_start, period_end)
    if initial_balance <= 0:
        raise ValueError("initial_balance must be positive")
    data = validate_ohlcv(candles)
    _assert_candles_within_period(data, start, end)
    _assert_trades_within_period(result.trades, start, end)

    volatility = (
        causal_volatility_regimes(data, volatility_settings)
        if precomputed_volatility is None
        else _validated_precomputed_volatility(precomputed_volatility, data)
    ).reset_index(drop=True)
    regime_by_time = {
        timestamp.to_pydatetime(): str(regime)
        for timestamp, regime in zip(
            volatility["time"], volatility["volatility_regime"], strict=True
        )
    }

    labelled = [
        _labelled_trade(trade, regime_by_time.get(_as_utc(trade.entry_time), "unavailable"))
        for trade in result.trades
    ]
    summaries = {
        "complete": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            **backtest_summary(result, symbol=symbol),
        },
        "by_year": _calendar_summaries(
            labelled, start, end, "year", initial_balance, symbol
        ),
        "by_quarter": _calendar_summaries(
            labelled, start, end, "quarter", initial_balance, symbol
        ),
        "by_month": _calendar_summaries(
            labelled, start, end, "month", initial_balance, symbol
        ),
        "by_direction": _category_summaries(
            labelled,
            "direction",
            ("BUY", "SELL"),
            initial_balance,
            symbol,
        ),
        "by_session": _category_summaries(
            labelled,
            "session",
            ("off_session", "london", "new_york", "london_new_york"),
            initial_balance,
            symbol,
        ),
        "by_volatility_regime": _category_summaries(
            labelled,
            "volatility_regime",
            ("low", "normal", "high", "unavailable"),
            initial_balance,
            symbol,
        ),
    }
    return {
        "period": {
            "name": "development",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "end_exclusive": True,
            "post_selection_data_used": False,
        },
        "attribution_basis": "trade_entry_time",
        "subgroup_drawdown_basis": "ordered subgroup net PnL; no strategy rerun or balance reset",
        "session_definition": "DST-aware Europe/London and America/New_York local 08:00-13:00",
        "volatility_regime_definition": volatility_settings.as_dict(),
        "summaries": summaries,
        "statistical_robustness": statistical_robustness_report(
            result.trades,
            period_start=start,
            period_end=end,
            settings=statistical_settings,
        ),
        "trades": [item["record"] for item in labelled],
    }


def _labelled_trade(trade: BacktestTrade, volatility_regime: str) -> dict[str, Any]:
    entry = _as_utc(trade.entry_time)
    record = trade_record(trade)
    labels = {
        "year": f"{entry.year:04d}",
        "quarter": f"{entry.year:04d}-Q{((entry.month - 1) // 3) + 1}",
        "month": f"{entry.year:04d}-{entry.month:02d}",
        "direction": trade.direction.value,
        "session": session_name(entry),
        "volatility_regime": volatility_regime,
    }
    record["diagnostic_labels"] = labels
    return {"trade": trade, "record": record, **labels}


def _calendar_summaries(
    labelled: Sequence[Mapping[str, Any]],
    start: datetime,
    end: datetime,
    dimension: str,
    initial_balance: float,
    symbol: str,
) -> list[dict[str, object]]:
    labels = _calendar_labels(start, end, dimension)
    return [
        {
            "group": label,
            **_summary_for_label(labelled, dimension, label, initial_balance, symbol),
        }
        for label in labels
    ]


def _category_summaries(
    labelled: Sequence[Mapping[str, Any]],
    dimension: str,
    categories: Sequence[str],
    initial_balance: float,
    symbol: str,
) -> list[dict[str, object]]:
    observed = {str(item[dimension]) for item in labelled}
    ordered = list(dict.fromkeys((*categories, *sorted(observed.difference(categories)))))
    return [
        {
            "group": label,
            **_summary_for_label(labelled, dimension, label, initial_balance, symbol),
        }
        for label in ordered
    ]


def _summary_for_label(
    labelled: Sequence[Mapping[str, Any]],
    dimension: str,
    label: str,
    initial_balance: float,
    symbol: str,
) -> dict[str, object]:
    trades = [item["trade"] for item in labelled if item[dimension] == label]
    subgroup = _result_for_trades(trades, initial_balance)
    summary = backtest_summary(subgroup, symbol=symbol)
    # Rejected strategy intents cannot be attributed to completed-trade groups.
    summary["rejected_intent_count"] = None
    return summary


def _result_for_trades(
    trades: Iterable[BacktestTrade], initial_balance: float
) -> BacktestResult:
    ordered = tuple(sorted(trades, key=lambda trade: (trade.exit_time, trade.entry_time)))
    equity = [initial_balance]
    running = initial_balance
    for trade in ordered:
        running = fsum((running, trade.net_pnl))
        equity.append(running)
    return BacktestResult(ordered, (), pd.DataFrame({"equity": equity}))


def _calendar_labels(start: datetime, end: datetime, dimension: str) -> list[str]:
    final = end - timedelta(microseconds=1)
    year, month = start.year, start.month
    months: list[tuple[int, int]] = []
    while (year, month) <= (final.year, final.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    if dimension == "month":
        return [f"{year:04d}-{month:02d}" for year, month in months]
    if dimension == "quarter":
        return list(
            dict.fromkeys(
                f"{year:04d}-Q{((month - 1) // 3) + 1}" for year, month in months
            )
        )
    if dimension == "year":
        return list(dict.fromkeys(f"{year:04d}" for year, _ in months))
    raise ValueError(f"unsupported calendar dimension: {dimension}")


def _validated_precomputed_volatility(
    volatility: pd.DataFrame, candles: pd.DataFrame
) -> pd.DataFrame:
    required = {"time", "volatility_regime"}
    if not required.issubset(volatility.columns):
        raise ValueError(f"precomputed volatility is missing columns: {sorted(required - set(volatility.columns))}")
    result = volatility.copy().reset_index(drop=True)
    if not isinstance(result["time"].dtype, pd.DatetimeTZDtype):
        raise ValueError("precomputed volatility timestamps must be timezone-aware")
    result["time"] = result["time"].dt.tz_convert("UTC")
    if not result["time"].equals(candles["time"].reset_index(drop=True)):
        raise ValueError("precomputed volatility must align one-to-one with evaluation candles")
    valid_labels = {"low", "normal", "high", "unavailable"}
    invalid = set(result["volatility_regime"].astype(str)).difference(valid_labels)
    if invalid:
        raise ValueError(f"precomputed volatility contains unknown regimes: {sorted(invalid)}")
    return result


def _assert_candles_are_development_only(candles: pd.DataFrame) -> None:
    _assert_candles_within_period(candles, DEVELOPMENT_START, DEVELOPMENT_END)


def _assert_candles_within_period(
    candles: pd.DataFrame, start: datetime, end: datetime
) -> None:
    timestamps = candles["time"]
    if (timestamps < pd.Timestamp(start)).any() or (timestamps >= pd.Timestamp(end)).any():
        raise SplitIsolationError(
            "market data contains observations outside the permitted development period"
        )


def _assert_trades_within_period(
    trades: Iterable[BacktestTrade], start: datetime, end: datetime
) -> None:
    for trade in trades:
        entry, exit_time = _as_utc(trade.entry_time), _as_utc(trade.exit_time)
        if not (start <= entry < end) or not (start <= exit_time < end):
            raise SplitIsolationError(
                "backtest result contains a trade outside the permitted development period"
            )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SplitIsolationError("trade timestamps must be timezone-aware")
    return value.astimezone(UTC)
