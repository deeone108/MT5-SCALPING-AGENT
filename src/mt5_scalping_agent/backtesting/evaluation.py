"""Common, deterministic strategy-evaluation contract for the bot tournament.

This layer normalizes strategy construction and metadata only. It does not
select winners, tune parameters, access market data, or submit broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Mapping

import pandas as pd

from mt5_scalping_agent.backtesting.engine import TradeIntent
from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.backtesting.trend_scalper import TrendScalperBacktestStrategy
from mt5_scalping_agent.strategies.xau60 import (
    CRTTBSAdapter,
    SMCScalperAdapter,
    TrendBreakTraumaAdapter,
)

_BASE_EVALUATION_COLUMNS = frozenset(
    {"time", "open", "high", "low", "close", "tick_volume"}
)


@dataclass(frozen=True)
class StrategyEvaluationSpec:
    """Machine-readable fixed strategy contract used by the tournament harness."""

    name: str
    evaluation_timeframe: str
    required_columns: frozenset[str]
    minimum_history_bars: int
    stateful: bool
    source: str
    supported_symbols: tuple[str, ...] | None = None
    context_timeframes: tuple[str, ...] = ()
    parameters_frozen: bool = True

    def supports_symbol(self, symbol: str) -> bool:
        if self.supported_symbols is None:
            return True
        normalized = symbol.strip().upper()
        return normalized in self.supported_symbols


@dataclass(frozen=True)
class EvaluationBuildContext:
    """Inputs needed to create a fresh strategy instance for one independent run."""

    symbol: str
    point: float = 0.0
    spread_points: float = 0.0
    context_candles: Mapping[str, pd.DataFrame] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.point < 0:
            raise ValueError("point must not be negative")
        if self.spread_points < 0:
            raise ValueError("spread_points must not be negative")


class XAU60BacktestStrategy:
    """Adapt one pinned XAU-60 SignalProposal strategy to TradeIntent."""

    uses_latest_candle_only = True

    def __init__(self, adapter: Any, symbol: str = "XAUUSD") -> None:
        normalized = symbol.strip().upper()
        if normalized != "XAUUSD":
            raise ValueError("pinned XAU-60 strategies support exactly XAUUSD")
        self._adapter = adapter
        self._symbol = normalized
        self.required_history_bars = int(adapter.minimum_bars)
        self.timeframe = str(adapter.timeframe)
        self.interval: timedelta = adapter.interval

    def __call__(self, history: pd.DataFrame) -> TradeIntent | None:
        if history.empty:
            return None
        frame = history.copy()
        if "volume" not in frame.columns and "tick_volume" in frame.columns:
            frame["volume"] = frame["tick_volume"]
        missing = set(self._adapter.required_columns).difference(frame.columns)
        if missing:
            raise ValueError(
                f"XAU-60 evaluation frame missing required columns: {sorted(missing)}"
            )
        observed_at = frame["time"].iloc[-1].to_pydatetime() + self.interval
        proposal = self._adapter.propose(self._symbol, frame, observed_at)
        return TradeIntent.from_signal(proposal)


StrategyFactory = Callable[[EvaluationBuildContext], Callable[[pd.DataFrame], TradeIntent | None]]


_INTERNAL_METADATA: dict[str, tuple[int, bool]] = {
    "london_range_breakout": (1, True),
    "bollinger_mean_reversion": (21, False),
    "donchian_breakout": (21, False),
    "moving_average_crossover": (21, False),
    "atr_filter": (21, False),
    "new_york_reversal": (21, False),
    "new_york_bollinger_rsi_reversal": (21, False),
    "new_york_opening_range_breakout": (21, True),
    "double_bollinger_breakout": (21, False),
    "rsi_trend_breakout": (22, False),
    "atr_filtered_mean_reversion": (22, False),
    "new_york_opening_range_retest": (21, True),
    "previous_day_range_breakout": (1, True),
    "new_york_bollinger_reentry": (22, True),
}


def _internal_specs() -> dict[str, StrategyEvaluationSpec]:
    return {
        name: StrategyEvaluationSpec(
            name=name,
            evaluation_timeframe="M1",
            required_columns=_BASE_EVALUATION_COLUMNS,
            minimum_history_bars=minimum,
            stateful=stateful,
            source="internal_fixed_rule",
        )
        for name, (minimum, stateful) in _INTERNAL_METADATA.items()
    }


def _xau60_spec(
    name: str,
    adapter_type: type,
    *,
    required_columns: frozenset[str],
) -> StrategyEvaluationSpec:
    return StrategyEvaluationSpec(
        name=name,
        evaluation_timeframe=str(adapter_type.timeframe),
        required_columns=required_columns,
        minimum_history_bars=int(adapter_type.minimum_bars),
        stateful=True,
        source="xau60_pinned",
        supported_symbols=("XAUUSD",),
    )


EVALUATION_STRATEGIES: dict[str, StrategyEvaluationSpec] = {
    **_internal_specs(),
    "trend_scalper": StrategyEvaluationSpec(
        name="trend_scalper",
        evaluation_timeframe="M1",
        context_timeframes=("M5",),
        required_columns=_BASE_EVALUATION_COLUMNS,
        minimum_history_bars=34,
        stateful=True,
        source="internal_trend_scalper",
    ),
    "xau60_smc_scalper_v2_1": _xau60_spec(
        "xau60_smc_scalper_v2_1",
        SMCScalperAdapter,
        required_columns=_BASE_EVALUATION_COLUMNS | {"spread"},
    ),
    "xau60_trend_break_trauma_v2_1": _xau60_spec(
        "xau60_trend_break_trauma_v2_1",
        TrendBreakTraumaAdapter,
        required_columns=_BASE_EVALUATION_COLUMNS,
    ),
    "xau60_crt_tbs_v2_1": _xau60_spec(
        "xau60_crt_tbs_v2_1",
        CRTTBSAdapter,
        required_columns=_BASE_EVALUATION_COLUMNS,
    ),
}


def evaluation_spec(name: str) -> StrategyEvaluationSpec:
    """Return a fixed strategy descriptor or fail explicitly."""
    try:
        return EVALUATION_STRATEGIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown evaluation strategy: {name}") from exc


def build_evaluation_strategy(
    name: str,
    context: EvaluationBuildContext,
) -> Callable[[pd.DataFrame], TradeIntent | None]:
    """Create a fresh, independent strategy instance for one backtest run."""
    spec = evaluation_spec(name)
    symbol = context.symbol.strip().upper()
    if not spec.supports_symbol(symbol):
        raise ValueError(f"{name} does not support symbol {symbol}")

    if name in STRATEGIES:
        return STRATEGIES[name]()

    if name == "trend_scalper":
        if context.point <= 0:
            raise ValueError("trend_scalper requires a positive instrument point")
        try:
            m5 = context.context_candles["M5"]
        except KeyError as exc:
            raise ValueError("trend_scalper requires M5 context candles") from exc
        return TrendScalperBacktestStrategy(
            symbol=symbol,
            m5_candles=m5,
            point=context.point,
            spread_points=context.spread_points,
        )

    adapter_types = {
        "xau60_smc_scalper_v2_1": SMCScalperAdapter,
        "xau60_trend_break_trauma_v2_1": TrendBreakTraumaAdapter,
        "xau60_crt_tbs_v2_1": CRTTBSAdapter,
    }
    try:
        adapter_type = adapter_types[name]
    except KeyError as exc:  # Registry and builder must evolve together.
        raise RuntimeError(f"no evaluation builder registered for {name}") from exc
    return XAU60BacktestStrategy(adapter_type(), symbol=symbol)
