"""Event-driven candle backtesting with conservative execution assumptions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from math import fsum, inf, isclose

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.domain import SignalProposal, TradeDirection
from mt5_scalping_agent.risk import (
    AccountRiskState,
    RiskEngine,
    RiskStateTracker,
    SymbolRiskSpec,
    TradePlan,
)


class PositionSizingMode(str, Enum):
    """Explicit simulation sizing policies; fixed lots are research diagnostics only."""

    RISK_PERCENT = "risk_percent"
    RESEARCH_FIXED_LOT = "research_fixed_lot"


class BacktestConfig(BaseModel):
    """Explicit, reproducible market-friction assumptions for a simulation."""

    model_config = ConfigDict(frozen=True)

    initial_balance: float = Field(gt=0)
    spread_points: float = Field(default=0.0, ge=0)
    slippage_points: float = Field(default=0.0, ge=0)
    commission_per_lot_per_side: float = Field(default=0.0, ge=0)
    position_sizing_mode: PositionSizingMode = PositionSizingMode.RISK_PERCENT
    fixed_volume_lots: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_position_sizing(self) -> BacktestConfig:
        if self.position_sizing_mode is PositionSizingMode.RESEARCH_FIXED_LOT:
            if self.fixed_volume_lots is None:
                raise ValueError(
                    "fixed_volume_lots is required for research_fixed_lot sizing"
                )
        elif self.fixed_volume_lots is not None:
            raise ValueError(
                "fixed_volume_lots is only valid for research_fixed_lot sizing"
            )
        return self

class EntryEconomicsConstraints(BaseModel):
    """Strategy-declared plan floors rechecked at the simulated entry price."""

    model_config = ConfigDict(frozen=True)

    minimum_risk_distance: float = Field(gt=0)
    minimum_reward_distance: float = Field(gt=0)
    reference_cost_distance: float = Field(gt=0)
    minimum_cost_adjusted_reward_risk: float = Field(gt=0)
    maximum_spread_points: float = Field(gt=0)
    maximum_all_in_cost_distance: float = Field(gt=0)
    required_entry_delay_seconds: float = Field(gt=0)


class TradeIntent(BaseModel):
    """A strategy's planned stop/target; entered only on the next candle."""

    model_config = ConfigDict(frozen=True)

    direction: TradeDirection
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    target_reward_risk_multiple: float | None = Field(default=None, gt=0)
    maximum_holding_duration: timedelta | None = Field(default=None, gt=timedelta(0))
    maximum_candle_gap: timedelta | None = Field(default=None, gt=timedelta(0))
    entry_economics: EntryEconomicsConstraints | None = None

    @classmethod
    def from_signal(cls, proposal: SignalProposal) -> TradeIntent | None:
        """Convert an actionable proposal into a backtest intent without execution."""
        if proposal.direction is TradeDirection.NO_TRADE:
            return None
        return cls(
            direction=proposal.direction,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
        )

    @model_validator(mode="after")
    def validate_direction(self) -> TradeIntent:
        if self.direction is TradeDirection.NO_TRADE:
            raise ValueError("trade intent must be BUY or SELL")
        return self


@dataclass(frozen=True)
class BacktestTrade:
    """A completed simulated trade with explicit pre-cost economics."""

    # Keep the original fields first so existing positional construction remains valid.
    direction: TradeDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    volume_lots: float
    gross_pnl: float
    net_pnl: float
    exit_reason: str
    symbol: str = ""
    stop_price: float | None = None
    target_price: float | None = None
    reference_entry_price: float | None = None
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    commission: float = 0.0
    total_transaction_cost: float | None = None
    holding_duration: timedelta | None = None
    mae: float | None = None
    mfe: float | None = None
    spread_cost_per_point: float = 0.0

    def __post_init__(self) -> None:
        total_cost = fsum((self.spread_cost, self.slippage_cost, self.commission))
        if min(self.spread_cost, self.slippage_cost, self.commission, self.spread_cost_per_point) < 0:
            raise ValueError("transaction costs must not be negative")
        if self.total_transaction_cost is None:
            object.__setattr__(self, "total_transaction_cost", total_cost)
        elif not isclose(self.total_transaction_cost, total_cost, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("total_transaction_cost must equal spread, slippage, and commission costs")

        duration = self.exit_time - self.entry_time
        if duration.total_seconds() < 0:
            raise ValueError("exit_time must not precede entry_time")
        if self.holding_duration is None:
            object.__setattr__(self, "holding_duration", duration)
        elif self.holding_duration != duration:
            raise ValueError("holding_duration must equal exit_time - entry_time")

        if not isclose(self.gross_pnl - total_cost, self.net_pnl, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("gross PnL minus transaction costs must equal net PnL")


@dataclass(frozen=True)
class BacktestResult:
    """Completed simulation output and consistent aggregate trade economics."""

    trades: tuple[BacktestTrade, ...]
    rejected_intents: tuple[str, ...]
    equity_curve: pd.DataFrame
    final_risk_state: AccountRiskState | None = None

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def accepted_trade_count(self) -> int:
        """Return intents accepted by risk and completed by the simulator."""
        return len(self.trades)

    @property
    def emitted_signal_count(self) -> int:
        """Return every strategy intent observed while the simulator was flat."""
        return len(self.trades) + len(self.rejected_intents)

    @property
    def total_lots(self) -> float:
        return fsum(trade.volume_lots for trade in self.trades)

    @property
    def gross_pnl(self) -> float:
        return fsum(trade.gross_pnl for trade in self.trades)

    @property
    def total_spread_cost(self) -> float:
        return fsum(trade.spread_cost for trade in self.trades)

    @property
    def total_slippage_cost(self) -> float:
        return fsum(trade.slippage_cost for trade in self.trades)

    @property
    def total_commission(self) -> float:
        return fsum(trade.commission for trade in self.trades)

    @property
    def total_transaction_cost(self) -> float:
        return fsum(float(trade.total_transaction_cost or 0.0) for trade in self.trades)

    @property
    def net_profit(self) -> float:
        return fsum(trade.net_pnl for trade in self.trades)

    @property
    def gross_expectancy_per_trade(self) -> float | None:
        return self.gross_pnl / self.trade_count if self.trades else None

    @property
    def net_expectancy_per_trade(self) -> float | None:
        return self.net_profit / self.trade_count if self.trades else None

    @property
    def average_winner(self) -> float | None:
        winners = [trade.net_pnl for trade in self.trades if trade.net_pnl > 0]
        return fsum(winners) / len(winners) if winners else None

    @property
    def average_loser(self) -> float | None:
        losers = [trade.net_pnl for trade in self.trades if trade.net_pnl < 0]
        return fsum(losers) / len(losers) if losers else None

    @property
    def win_rate(self) -> float | None:
        if not self.trades:
            return None
        return sum(trade.net_pnl > 0 for trade in self.trades) / len(self.trades)

    @property
    def profit_factor(self) -> float | None:
        if not self.trades:
            return None
        gross_profit = fsum(trade.net_pnl for trade in self.trades if trade.net_pnl > 0)
        gross_loss = -fsum(trade.net_pnl for trade in self.trades if trade.net_pnl < 0)
        return inf if gross_loss == 0 and gross_profit > 0 else (gross_profit / gross_loss if gross_loss else None)

    @property
    def payoff_ratio(self) -> float | None:
        average_winner, average_loser = self.average_winner, self.average_loser
        if average_winner is None or average_loser is None:
            return None
        return average_winner / abs(average_loser)

    @property
    def max_drawdown(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        equity = self.equity_curve["equity"]
        return float((equity.cummax() - equity).max())

    @property
    def average_holding_duration(self) -> timedelta | None:
        if not self.trades:
            return None
        seconds = fsum(
            trade.holding_duration.total_seconds()
            for trade in self.trades
            if trade.holding_duration is not None
        )
        return timedelta(seconds=seconds / self.trade_count)

    @property
    def break_even_transaction_cost_per_trade(self) -> float | None:
        """Return the nonnegative average all-in cost that leaves net PnL at zero."""
        expectancy = self.gross_expectancy_per_trade
        return expectancy if expectancy is not None and expectancy >= 0 else None

    @property
    def break_even_spread_points(self) -> float | None:
        """Return the constant round-trip spread that leaves aggregate net PnL at zero."""
        spread_cost_per_point = fsum(trade.spread_cost_per_point for trade in self.trades)
        available_for_spread = self.gross_pnl - self.total_slippage_cost - self.total_commission
        if spread_cost_per_point <= 0 or available_for_spread < 0:
            return None
        return available_for_spread / spread_cost_per_point


Strategy = Callable[[pd.DataFrame], TradeIntent | None]

@dataclass(frozen=True)
class _PendingIntent:
    intent: TradeIntent
    generated_at: datetime


@dataclass
class _OpenTrade:
    intent: TradeIntent
    entry_time: datetime
    entry_price: float
    volume_lots: float
    reference_entry_price: float
    last_candle_time: datetime
    mae: float = 0.0
    mfe: float = 0.0


class CandleBacktester:
    """A single-position backtester that never exposes future candles to a strategy."""

    def __init__(self, config: BacktestConfig, risk_engine: RiskEngine, symbol: SymbolRiskSpec) -> None:
        self._config = config
        self._risk_engine = risk_engine
        self._symbol = symbol

    def run(self, candles: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        data = validate_ohlcv(candles)
        tracker = RiskStateTracker(
            self._config.initial_balance,
            reset_consecutive_losses_each_utc_day=(
                self._risk_engine.limits.reset_consecutive_losses_each_utc_day
            ),
        )
        trades: list[BacktestTrade] = []
        rejections: list[str] = []
        curve: list[dict[str, object]] = []
        pending: _PendingIntent | None = None
        position: _OpenTrade | None = None

        for index, candle in data.iterrows():
            timestamp = candle["time"].to_pydatetime()
            if pending is not None:
                market_data_age = (timestamp - pending.generated_at).total_seconds()
                account = tracker.snapshot(
                    timestamp,
                    symbol=self._symbol.symbol,
                    market_data_age_seconds=market_data_age,
                )
                position, rejection = self._open_next_candle(
                    pending.intent,
                    candle,
                    timestamp,
                    account,
                )
                pending = None
                if position is not None:
                    tracker.record_trade_open(
                        timestamp,
                        self._symbol.symbol,
                        position.volume_lots,
                    )
                if rejection:
                    rejections.append(rejection)

            if position is not None:
                maximum_gap = position.intent.maximum_candle_gap
                candle_gap = timestamp - position.last_candle_time
                if maximum_gap is not None and candle_gap > maximum_gap:
                    raise ValueError(
                        "open position encountered a candle gap larger than its declared maximum"
                    )
                position.last_candle_time = timestamp
                self._update_excursions(position, candle)
                closed = self._exit_if_triggered(position, candle, timestamp)
                if closed is not None:
                    trades.append(closed)
                    tracker.record_trade_close(
                        timestamp,
                        self._symbol.symbol,
                        closed.volume_lots,
                        closed.net_pnl,
                    )
                    position = None

            mark_to_market_pnl = (
                self._mark_to_market_pnl(position, float(candle["close"]))
                if position is not None
                else 0.0
            )
            state = tracker.snapshot(
                timestamp,
                symbol=self._symbol.symbol,
                mark_to_market_pnl=mark_to_market_pnl,
            )
            self._record_curve_point(curve, timestamp, state)

            # The strategy sees only candles available at this close. Its intent opens next bar.
            if position is None and pending is None and index < data.index[-1]:
                is_evaluation_time = getattr(strategy, "is_evaluation_time", None)
                if not callable(is_evaluation_time) or is_evaluation_time(timestamp):
                    required_history_bars = getattr(
                        strategy,
                        "required_history_bars",
                        1 if getattr(strategy, "uses_latest_candle_only", False) else 0,
                    )
                    position_in_data = data.index.get_loc(index)
                    history = (
                        data.iloc[
                            max(0, position_in_data - required_history_bars + 1) : position_in_data + 1
                        ].copy()
                        if required_history_bars
                        else data.loc[:index].copy()
                    )
                    intent = strategy(history)
                    if intent is not None:
                        pending = _PendingIntent(intent, timestamp)
        if position is not None:
            final_candle = data.iloc[-1]
            final_timestamp = final_candle["time"].to_pydatetime()
            closed = self._close_at_end(position, final_candle, final_timestamp)
            trades.append(closed)
            tracker.record_trade_close(
                final_timestamp,
                self._symbol.symbol,
                closed.volume_lots,
                closed.net_pnl,
            )
            state = tracker.snapshot(final_timestamp, symbol=self._symbol.symbol)
            self._record_curve_point(curve, final_timestamp, state)

        final_timestamp = data["time"].iloc[-1].to_pydatetime()
        final_state = tracker.snapshot(final_timestamp, symbol=self._symbol.symbol)
        return BacktestResult(
            tuple(trades),
            tuple(rejections),
            pd.DataFrame(curve),
            final_state,
        )

    def _open_next_candle(
        self,
        intent: TradeIntent,
        candle: pd.Series,
        timestamp: datetime,
        account: AccountRiskState,
    ) -> tuple[_OpenTrade | None, str | None]:
        entry = self._entry_price(intent.direction, float(candle["open"]))
        try:
            intent = self._resolve_entry_relative_target(intent, entry)
        except ValueError as error:
            return None, f"invalid entry-relative target: {error}"
        economics_rejections = self._entry_economics_rejections(intent, entry, account)
        if economics_rejections:
            return None, "; ".join(economics_rejections)
        try:
            plan = TradePlan(
                symbol=self._symbol.symbol,
                direction=intent.direction,
                entry_price=entry,
                stop_loss=intent.stop_loss,
                take_profit=intent.take_profit,
                spread_points=self._config.spread_points,
            )
        except ValueError as error:
            return None, f"invalid next-candle trade plan: {error}"
        if self._config.position_sizing_mode is PositionSizingMode.RESEARCH_FIXED_LOT:
            fixed_volume = self._config.fixed_volume_lots
            if fixed_volume is None:  # Defended by BacktestConfig validation.
                raise RuntimeError("research fixed-lot sizing has no configured volume")
            decision = self._risk_engine.assess_research_fixed_volume(
                plan,
                account,
                self._symbol,
                fixed_volume,
            )
        else:
            decision = self._risk_engine.assess(plan, account, self._symbol)
        if not decision.allowed or decision.volume_lots is None:
            return None, "; ".join(decision.reasons)
        return _OpenTrade(
            intent,
            timestamp,
            entry,
            decision.volume_lots,
            float(candle["open"]),
            timestamp,
        ), None

    @staticmethod
    def _resolve_entry_relative_target(intent: TradeIntent, entry: float) -> TradeIntent:
        multiple = intent.target_reward_risk_multiple
        if multiple is None:
            return intent
        if intent.direction is TradeDirection.BUY:
            risk = entry - intent.stop_loss
            if risk <= 0:
                raise ValueError("BUY entry must remain above stop")
            target = entry + risk * multiple
        else:
            risk = intent.stop_loss - entry
            if risk <= 0:
                raise ValueError("SELL entry must remain below stop")
            target = entry - risk * multiple
        if target <= 0:
            raise ValueError("resolved target must be positive")
        return intent.model_copy(update={"take_profit": target})
    def _entry_economics_rejections(
        self,
        intent: TradeIntent,
        entry_price: float,
        account: AccountRiskState,
    ) -> list[str]:
        constraints = intent.entry_economics
        if constraints is None:
            return []
        risk_distance = (
            entry_price - intent.stop_loss
            if intent.direction is TradeDirection.BUY
            else intent.stop_loss - entry_price
        )
        reward_distance = (
            intent.take_profit - entry_price
            if intent.direction is TradeDirection.BUY
            else entry_price - intent.take_profit
        )
        tolerance = 1e-12
        reasons: list[str] = []
        if risk_distance + tolerance < constraints.minimum_risk_distance:
            reasons.append("actual-entry stop distance is below the strategy minimum")
        if reward_distance + tolerance < constraints.minimum_reward_distance:
            reasons.append("actual-entry reward distance is below the strategy minimum")
        if risk_distance > 0 and reward_distance > 0:
            adjusted = (
                (reward_distance - constraints.reference_cost_distance)
                / (risk_distance + constraints.reference_cost_distance)
            )
            if adjusted + tolerance < constraints.minimum_cost_adjusted_reward_risk:
                reasons.append("actual-entry cost-adjusted reward/risk is below the strategy minimum")
        if self._config.spread_points > constraints.maximum_spread_points + tolerance:
            reasons.append("spread exceeds the strategy maximum")
        value_per_price_unit_per_lot = self._symbol.tick_value / self._symbol.tick_size
        commission_distance = (
            2 * self._config.commission_per_lot_per_side
            / value_per_price_unit_per_lot
        )
        all_in_cost_distance = (
            (self._config.spread_points + self._config.slippage_points)
            * self._symbol.point
            + commission_distance
        )
        if all_in_cost_distance > constraints.maximum_all_in_cost_distance + tolerance:
            reasons.append("all-in cost exceeds the strategy maximum")
        delay = account.market_data_age_seconds
        if (
            delay is None
            or not isclose(
                delay,
                constraints.required_entry_delay_seconds,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            reasons.append("entry is not on the strategy-required next candle")
        return reasons

    def _mark_to_market_pnl(self, position: _OpenTrade, close_price: float) -> float:
        exit_price = close_price
        if position.intent.direction is TradeDirection.SELL:
            exit_price += self._config.spread_points * self._symbol.point
        price_difference = exit_price - position.entry_price
        signed_difference = (
            price_difference
            if position.intent.direction is TradeDirection.BUY
            else -price_difference
        )
        value_per_price_unit = (
            self._symbol.tick_value / self._symbol.tick_size * position.volume_lots
        )
        estimated_round_trip_commission = (
            self._config.commission_per_lot_per_side * position.volume_lots * 2
        )
        return signed_difference * value_per_price_unit - estimated_round_trip_commission

    @staticmethod
    def _record_curve_point(
        curve: list[dict[str, object]],
        timestamp: datetime,
        state: AccountRiskState,
    ) -> None:
        point = {
            "time": timestamp,
            "equity": state.equity,
            "balance": state.balance,
            "peak_equity": state.peak_equity,
            "drawdown": max(0.0, state.peak_equity - state.equity),
            "daily_realized_pnl": state.daily_realized_pnl,
            "weekly_realized_pnl": state.weekly_realized_pnl,
            "consecutive_losses": state.consecutive_losses,
            "trades_current_hour": state.trades_current_hour,
            "trades_current_day": state.trades_current_day,
            "open_position_count": state.open_position_count,
            "current_exposure_lots": state.current_exposure_lots,
            "symbol_exposure_lots": state.symbol_exposure_lots,
        }
        if curve and curve[-1]["time"] == timestamp:
            curve[-1] = point
        else:
            curve.append(point)

    def _update_excursions(self, position: _OpenTrade, candle: pd.Series) -> None:
        value_per_price_unit = (
            self._symbol.tick_value / self._symbol.tick_size * position.volume_lots
        )
        high, low = float(candle["high"]), float(candle["low"])
        if position.intent.direction is TradeDirection.BUY:
            adverse = (low - position.reference_entry_price) * value_per_price_unit
            favorable = (high - position.reference_entry_price) * value_per_price_unit
        else:
            adverse = (position.reference_entry_price - high) * value_per_price_unit
            favorable = (position.reference_entry_price - low) * value_per_price_unit
        position.mae = min(position.mae, adverse)
        position.mfe = max(position.mfe, favorable)

    def _exit_if_triggered(
        self,
        position: _OpenTrade,
        candle: pd.Series,
        timestamp: datetime,
    ) -> BacktestTrade | None:
        high, low = float(candle["high"]), float(candle["low"])
        stop, target = position.intent.stop_loss, position.intent.take_profit
        spread = self._config.spread_points * self._symbol.point

        if position.intent.direction is TradeDirection.BUY:
            if low <= stop:
                return self._close(position, timestamp, stop, "stop_loss")
            if high >= target:
                return self._close(position, timestamp, target, "take_profit")
        else:
            if high + spread >= stop:
                return self._close(position, timestamp, stop, "stop_loss")
            if low + spread <= target:
                return self._close(position, timestamp, target, "take_profit")
        maximum_holding = position.intent.maximum_holding_duration
        if maximum_holding is not None and timestamp - position.entry_time >= maximum_holding:
            exit_price = float(candle["close"])
            if position.intent.direction is TradeDirection.SELL:
                exit_price += spread
            return self._close(position, timestamp, exit_price, "time_exit")
        return None

    def _close_at_end(
        self,
        position: _OpenTrade,
        candle: pd.Series,
        timestamp: datetime,
    ) -> BacktestTrade:
        exit_price = float(candle["close"])
        if position.intent.direction is TradeDirection.SELL:
            exit_price += self._config.spread_points * self._symbol.point
        return self._close(position, timestamp, exit_price, "end_of_data")

    def _entry_price(self, direction: TradeDirection, opening_price: float) -> float:
        friction = (
            self._config.spread_points + self._config.slippage_points
        ) * self._symbol.point
        return (
            opening_price + friction
            if direction is TradeDirection.BUY
            else opening_price - self._config.slippage_points * self._symbol.point
        )

    def _close(
        self,
        position: _OpenTrade,
        timestamp: datetime,
        exit_price: float,
        reason: str,
    ) -> BacktestTrade:
        price_difference = exit_price - position.entry_price
        signed_difference = (
            price_difference
            if position.intent.direction is TradeDirection.BUY
            else -price_difference
        )
        value_per_price_unit = (
            self._symbol.tick_value / self._symbol.tick_size * position.volume_lots
        )
        execution_pnl = signed_difference * value_per_price_unit
        spread_cost_per_point = self._symbol.point * value_per_price_unit
        spread_cost = self._config.spread_points * spread_cost_per_point
        slippage_cost = self._config.slippage_points * spread_cost_per_point
        commission = (
            self._config.commission_per_lot_per_side * position.volume_lots * 2
        )
        total_transaction_cost = fsum((spread_cost, slippage_cost, commission))
        gross_pnl = execution_pnl + spread_cost + slippage_cost
        net_pnl = gross_pnl - total_transaction_cost
        return BacktestTrade(
            direction=position.intent.direction,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            volume_lots=position.volume_lots,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            exit_reason=reason,
            symbol=self._symbol.symbol,
            stop_price=position.intent.stop_loss,
            target_price=position.intent.take_profit,
            reference_entry_price=position.reference_entry_price,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            commission=commission,
            total_transaction_cost=total_transaction_cost,
            holding_duration=timestamp - position.entry_time,
            mae=position.mae,
            mfe=position.mfe,
            spread_cost_per_point=spread_cost_per_point,
        )
