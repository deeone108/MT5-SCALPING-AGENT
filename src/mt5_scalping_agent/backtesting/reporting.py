"""Consistent, JSON-safe backtest economics reporting."""

from __future__ import annotations

from collections import Counter
from math import inf
from typing import Any

from mt5_scalping_agent.backtesting.engine import BacktestResult, BacktestTrade


def trade_record(trade: BacktestTrade) -> dict[str, Any]:
    """Serialize one completed trade with explicit units and cost decomposition."""
    return {
        "symbol": trade.symbol,
        "direction": trade.direction.value,
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "entry_price": trade.entry_price,
        "reference_entry_price": trade.reference_entry_price,
        "exit_price": trade.exit_price,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "volume_lots": trade.volume_lots,
        "gross_pnl": trade.gross_pnl,
        "spread_cost": trade.spread_cost,
        "slippage_cost": trade.slippage_cost,
        "commission": trade.commission,
        "total_transaction_cost": trade.total_transaction_cost,
        "net_pnl": trade.net_pnl,
        "holding_duration_seconds": (
            trade.holding_duration.total_seconds()
            if trade.holding_duration is not None
            else None
        ),
        "mae": trade.mae,
        "mfe": trade.mfe,
        "exit_reason": trade.exit_reason,
        "spread_cost_per_point": trade.spread_cost_per_point,
    }


def backtest_summary(
    result: BacktestResult,
    *,
    symbol: str | None = None,
) -> dict[str, object]:
    """Return the canonical aggregate economics block used by research reports."""
    durations = [
        trade.holding_duration.total_seconds()
        for trade in result.trades
        if trade.holding_duration is not None
    ]
    maes = [trade.mae for trade in result.trades if trade.mae is not None]
    mfes = [trade.mfe for trade in result.trades if trade.mfe is not None]
    resolved_symbol = symbol
    if resolved_symbol is None:
        symbols = {trade.symbol for trade in result.trades if trade.symbol}
        resolved_symbol = next(iter(symbols)) if len(symbols) == 1 else None

    rejection_reasons = Counter(
        reason.strip()
        for rejection in result.rejected_intents
        for reason in rejection.split(";")
        if reason.strip()
    )

    return {
        "symbol": resolved_symbol,
        "emitted_signal_count": result.emitted_signal_count,
        "accepted_trade_count": result.accepted_trade_count,
        "trade_count": result.trade_count,
        "total_lots": result.total_lots,
        "gross_pnl": result.gross_pnl,
        "total_spread_cost": result.total_spread_cost,
        "total_slippage_cost": result.total_slippage_cost,
        "total_commission": result.total_commission,
        "total_transaction_cost": result.total_transaction_cost,
        "net_pnl": result.net_profit,
        # Preserve the original report field during migration.
        "net_profit": result.net_profit,
        "gross_expectancy_per_trade": result.gross_expectancy_per_trade,
        "net_expectancy_per_trade": result.net_expectancy_per_trade,
        "average_winner": result.average_winner,
        "average_loser": result.average_loser,
        "win_rate": result.win_rate,
        "payoff_ratio": result.payoff_ratio,
        "profit_factor": (
            "infinity" if result.profit_factor == inf else result.profit_factor
        ),
        "max_drawdown": result.max_drawdown,
        "average_holding_duration_seconds": (
            sum(durations) / len(durations) if durations else None
        ),
        "average_mae": sum(maes) / len(maes) if maes else None,
        "average_mfe": sum(mfes) / len(mfes) if mfes else None,
        "break_even_transaction_cost_per_trade": (
            result.break_even_transaction_cost_per_trade
        ),
        "break_even_spread_points": result.break_even_spread_points,
        "rejected_intent_count": len(result.rejected_intents),
        "rejected_intent_reason_counts": dict(sorted(rejection_reasons.items())),
    }
