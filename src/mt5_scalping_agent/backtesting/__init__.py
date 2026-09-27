"""Historical execution simulation and reporting."""

from mt5_scalping_agent.backtesting.engine import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    CandleBacktester,
    EntryEconomicsConstraints,
    PositionSizingMode,
    TradeIntent,
)
from mt5_scalping_agent.backtesting.reporting import backtest_summary, trade_record

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "CandleBacktester",
    "EntryEconomicsConstraints",
    "PositionSizingMode",
    "TradeIntent",
    "backtest_summary",
    "trade_record",
    "EVALUATION_STRATEGIES",
    "EvaluationBuildContext",
    "StrategyEvaluationSpec",
    "XAU60BacktestStrategy",
    "build_evaluation_strategy",
    "evaluation_spec",
]

from mt5_scalping_agent.backtesting.evaluation import (
    EVALUATION_STRATEGIES,
    EvaluationBuildContext,
    StrategyEvaluationSpec,
    XAU60BacktestStrategy,
    build_evaluation_strategy,
    evaluation_spec,
)
