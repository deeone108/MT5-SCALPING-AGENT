"""Deterministic trade-risk validation and symbol-aware position sizing."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isclose

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mt5_scalping_agent.domain import TradeDirection


class RiskConfigurationError(ValueError):
    """Raised when a risk model configuration is internally inconsistent."""


class SymbolRiskSpec(BaseModel):
    """Broker-provided contract values required for monetary risk calculations."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    point: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    tick_value: float = Field(gt=0)
    volume_min: float = Field(gt=0)
    volume_max: float = Field(gt=0)
    volume_step: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_volume_bounds(self) -> SymbolRiskSpec:
        if self.volume_min > self.volume_max:
            raise ValueError("volume_min must not exceed volume_max")
        return self


class AccountRiskState(BaseModel):
    """Immutable account and market state supplied to the risk authority."""

    model_config = ConfigDict(frozen=True)

    equity: float
    balance: float
    peak_equity: float = Field(gt=0)
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    daily_starting_equity: float | None = None
    weekly_starting_equity: float | None = None
    open_position_count: int = Field(default=0, ge=0)
    current_exposure_lots: float = Field(default=0.0, ge=0)
    symbol_exposure_lots: float = Field(default=0.0, ge=0)
    consecutive_losses: int = Field(default=0, ge=0)
    trades_current_hour: int = Field(default=0, ge=0)
    trades_current_day: int = Field(default=0, ge=0)
    market_data_age_seconds: float | None = Field(default=None, ge=0)


class TradePlan(BaseModel):
    """A complete planned trade, still independent of broker order submission."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    direction: TradeDirection
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    spread_points: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_directional_prices(self) -> TradePlan:
        if self.direction is TradeDirection.NO_TRADE:
            raise ValueError("a trade plan must be BUY or SELL")
        if self.direction is TradeDirection.BUY and not self.stop_loss < self.entry_price < self.take_profit:
            raise ValueError("BUY plan requires stop_loss < entry_price < take_profit")
        if self.direction is TradeDirection.SELL and not self.take_profit < self.entry_price < self.stop_loss:
            raise ValueError("SELL plan requires take_profit < entry_price < stop_loss")
        return self

    @property
    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_distance(self) -> float:
        return abs(self.take_profit - self.entry_price)

    @property
    def reward_risk_ratio(self) -> float:
        return self.reward_distance / self.risk_distance


class RiskLimits(BaseModel):
    """Research defaults; every limit requires backtest and demo validation."""

    model_config = ConfigDict(frozen=True)

    risk_percent_per_trade: float = Field(default=0.5, gt=0, le=100)
    max_daily_loss_percent: float = Field(default=2.0, gt=0, le=100)
    max_weekly_loss_percent: float = Field(default=5.0, gt=0, le=100)
    max_drawdown_percent: float = Field(default=10.0, gt=0, le=100)
    max_consecutive_losses: int = Field(default=3, ge=1)
    reset_consecutive_losses_each_utc_day: bool = True
    max_trades_per_hour: int = Field(default=20, ge=1)
    max_trades_per_day: int = Field(default=100, ge=1)
    max_open_positions: int = Field(default=1, ge=1)
    max_exposure_lots: float = Field(default=1.0, gt=0)
    max_symbol_exposure_lots: float | None = Field(default=None, gt=0)
    max_lot_size: float = Field(default=1.0, gt=0)
    min_reward_risk_ratio: float = Field(default=1.5, gt=0)
    max_spread_points: float = Field(default=3.0, gt=0)
    max_market_data_age_seconds: float = Field(default=300.0, gt=0)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
    volume_lots: float | None = None
    risk_amount: float | None = None
    reward_risk_ratio: float | None = None


class RiskEngine:
    """Final authority for risk acceptance; it has no broker execution capability."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()

    @property
    def limits(self) -> RiskLimits:
        """Expose immutable limits for manifests and compatible state adapters."""
        return self._limits

    def assess(self, plan: TradePlan, account: AccountRiskState, symbol: SymbolRiskSpec) -> RiskDecision:
        """Accept or reject a trade plan and calculate a conservative lot size."""
        reasons = self._rejection_reasons(plan, account, symbol)
        if reasons:
            return RiskDecision(False, tuple(reasons), reward_risk_ratio=plan.reward_risk_ratio)

        risk_amount = account.equity * self._limits.risk_percent_per_trade / 100
        loss_per_lot = plan.risk_distance * symbol.tick_value / symbol.tick_size
        raw_volume = risk_amount / loss_per_lot
        volume = self._normalize_volume(raw_volume, symbol)
        if volume is None:
            return RiskDecision(
                False,
                ("calculated position size is below the broker minimum volume",),
                risk_amount=risk_amount,
                reward_risk_ratio=plan.reward_risk_ratio,
            )
        if account.current_exposure_lots + volume > self._limits.max_exposure_lots:
            return RiskDecision(
                False,
                ("proposed position would exceed maximum exposure",),
                risk_amount=risk_amount,
                reward_risk_ratio=plan.reward_risk_ratio,
            )
        symbol_exposure_limit = (
            self._limits.max_symbol_exposure_lots or self._limits.max_exposure_lots
        )
        if account.symbol_exposure_lots + volume > symbol_exposure_limit:
            return RiskDecision(
                False,
                ("proposed position would exceed maximum symbol exposure",),
                risk_amount=risk_amount,
                reward_risk_ratio=plan.reward_risk_ratio,
            )

        actual_risk = volume * loss_per_lot
        return RiskDecision(True, (), volume, actual_risk, plan.reward_risk_ratio)

    def assess_research_fixed_volume(
        self,
        plan: TradePlan,
        account: AccountRiskState,
        symbol: SymbolRiskSpec,
        volume_lots: float,
    ) -> RiskDecision:
        """Assess fixed volume without portfolio-survival censorship.

        This simulation-only path separates raw signal economics from compounding
        position sizing. It preserves plan, market-data, reward/risk, broker-volume,
        single-position, and exposure checks. Account depletion and portfolio
        circuit breakers are intentionally nonbinding.
        """
        reasons = self._research_fixed_volume_rejection_reasons(
            plan, account, symbol, volume_lots
        )
        if reasons:
            return RiskDecision(
                False,
                tuple(reasons),
                reward_risk_ratio=plan.reward_risk_ratio,
            )
        loss_per_lot = plan.risk_distance * symbol.tick_value / symbol.tick_size
        return RiskDecision(
            True,
            (),
            volume_lots,
            volume_lots * loss_per_lot,
            plan.reward_risk_ratio,
        )

    def _research_fixed_volume_rejection_reasons(
        self,
        plan: TradePlan,
        account: AccountRiskState,
        symbol: SymbolRiskSpec,
        volume_lots: float,
    ) -> list[str]:
        reasons: list[str] = []
        if plan.symbol != symbol.symbol:
            reasons.append("trade plan symbol does not match symbol specification")
        if plan.spread_points > self._limits.max_spread_points:
            reasons.append("spread exceeds configured maximum")
        if (
            account.market_data_age_seconds is not None
            and account.market_data_age_seconds > self._limits.max_market_data_age_seconds
        ):
            reasons.append("market data is stale")
        if plan.reward_risk_ratio < self._limits.min_reward_risk_ratio:
            reasons.append("reward/risk ratio is below the configured minimum")
        if account.open_position_count >= self._limits.max_open_positions:
            reasons.append("maximum open positions has been reached")
        if volume_lots < symbol.volume_min:
            reasons.append("fixed research volume is below the broker minimum volume")
        if volume_lots > min(symbol.volume_max, self._limits.max_lot_size):
            reasons.append("fixed research volume exceeds the configured maximum volume")
        steps = volume_lots / symbol.volume_step
        if not isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
            reasons.append(
                "fixed research volume is not aligned to the broker volume step"
            )
        if (
            account.current_exposure_lots + volume_lots
            > self._limits.max_exposure_lots
        ):
            reasons.append("proposed position would exceed maximum exposure")
        symbol_exposure_limit = (
            self._limits.max_symbol_exposure_lots
            or self._limits.max_exposure_lots
        )
        if account.symbol_exposure_lots + volume_lots > symbol_exposure_limit:
            reasons.append("proposed position would exceed maximum symbol exposure")
        return reasons


    def _rejection_reasons(self, plan: TradePlan, account: AccountRiskState, symbol: SymbolRiskSpec) -> list[str]:
        reasons: list[str] = []
        if plan.symbol != symbol.symbol:
            reasons.append("trade plan symbol does not match symbol specification")
        if account.equity <= 0 or account.balance <= 0:
            reasons.append("account equity or balance is depleted")
        if plan.spread_points > self._limits.max_spread_points:
            reasons.append("spread exceeds configured maximum")
        if (
            account.market_data_age_seconds is not None
            and account.market_data_age_seconds > self._limits.max_market_data_age_seconds
        ):
            reasons.append("market data is stale")
        if plan.reward_risk_ratio < self._limits.min_reward_risk_ratio:
            reasons.append("reward/risk ratio is below the configured minimum")
        daily_base = account.daily_starting_equity or account.balance
        if account.daily_realized_pnl <= -(daily_base * self._limits.max_daily_loss_percent / 100):
            reasons.append("maximum daily loss has been reached")
        weekly_base = account.weekly_starting_equity or account.balance
        if account.weekly_realized_pnl <= -(weekly_base * self._limits.max_weekly_loss_percent / 100):
            reasons.append("maximum weekly loss has been reached")
        drawdown_percent = max(0.0, (account.peak_equity - account.equity) / account.peak_equity * 100)
        if drawdown_percent >= self._limits.max_drawdown_percent:
            reasons.append("maximum mark-to-market drawdown has been reached")
        if account.consecutive_losses >= self._limits.max_consecutive_losses:
            reasons.append("maximum consecutive losses has been reached")
        if account.trades_current_hour >= self._limits.max_trades_per_hour:
            reasons.append("maximum trades per hour has been reached")
        if account.trades_current_day >= self._limits.max_trades_per_day:
            reasons.append("maximum trades per day has been reached")
        if account.open_position_count >= self._limits.max_open_positions:
            reasons.append("maximum open positions has been reached")
        return reasons

    def _normalize_volume(self, raw_volume: float, symbol: SymbolRiskSpec) -> float | None:
        capped_volume = min(raw_volume, self._limits.max_lot_size, symbol.volume_max)
        steps = floor((capped_volume + 1e-12) / symbol.volume_step)
        normalized = round(steps * symbol.volume_step, 10)
        if normalized < symbol.volume_min:
            return None
        return normalized
