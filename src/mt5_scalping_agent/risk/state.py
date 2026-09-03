"""Reusable event-driven risk state for simulation and future adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isclose

from mt5_scalping_agent.risk.engine import AccountRiskState


class RiskStateError(RuntimeError):
    """Raised when position or risk-state events are internally inconsistent."""


@dataclass
class RiskStateTracker:
    """Track account protection state without broker or strategy dependencies."""

    initial_balance: float
    reset_consecutive_losses_each_utc_day: bool = True
    balance: float = field(init=False)
    peak_equity: float = field(init=False)
    consecutive_losses: int = field(default=0, init=False)
    _daily_realized_pnl: dict[date, float] = field(default_factory=dict, init=False)
    _weekly_realized_pnl: dict[tuple[int, int], float] = field(default_factory=dict, init=False)
    _daily_starting_equity: dict[date, float] = field(default_factory=dict, init=False)
    _weekly_starting_equity: dict[tuple[int, int], float] = field(default_factory=dict, init=False)
    _trades_by_hour: dict[datetime, int] = field(default_factory=dict, init=False)
    _trades_by_day: dict[date, int] = field(default_factory=dict, init=False)
    _open_positions: int = field(default=0, init=False)
    _symbol_exposure: dict[str, float] = field(default_factory=dict, init=False)
    _active_loss_day: date | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        self.balance = float(self.initial_balance)
        self.peak_equity = float(self.initial_balance)

    def snapshot(
        self,
        timestamp: datetime,
        *,
        symbol: str,
        mark_to_market_pnl: float = 0.0,
        market_data_age_seconds: float | None = None,
    ) -> AccountRiskState:
        """Return immutable current risk state and observe candle-close equity."""
        current = _as_utc(timestamp)
        if market_data_age_seconds is not None and market_data_age_seconds < 0:
            raise ValueError("market_data_age_seconds must not be negative")
        self._roll_periods(current)
        equity = self.balance + mark_to_market_pnl
        self.peak_equity = max(self.peak_equity, equity)
        day, week, hour = current.date(), _week_key(current), _hour_key(current)
        return AccountRiskState(
            equity=equity,
            balance=self.balance,
            peak_equity=self.peak_equity,
            daily_realized_pnl=self._daily_realized_pnl.get(day, 0.0),
            weekly_realized_pnl=self._weekly_realized_pnl.get(week, 0.0),
            daily_starting_equity=self._daily_starting_equity[day],
            weekly_starting_equity=self._weekly_starting_equity[week],
            open_position_count=self._open_positions,
            current_exposure_lots=sum(self._symbol_exposure.values()),
            symbol_exposure_lots=self._symbol_exposure.get(symbol, 0.0),
            consecutive_losses=self.consecutive_losses,
            trades_current_hour=self._trades_by_hour.get(hour, 0),
            trades_current_day=self._trades_by_day.get(day, 0),
            market_data_age_seconds=market_data_age_seconds,
        )

    def record_trade_open(self, timestamp: datetime, symbol: str, volume_lots: float) -> None:
        """Record one accepted entry after the risk engine approves it."""
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        if volume_lots <= 0:
            raise ValueError("volume_lots must be positive")
        current = _as_utc(timestamp)
        self._roll_periods(current)
        day, hour = current.date(), _hour_key(current)
        self._trades_by_hour[hour] = self._trades_by_hour.get(hour, 0) + 1
        self._trades_by_day[day] = self._trades_by_day.get(day, 0) + 1
        self._open_positions += 1
        self._symbol_exposure[symbol] = self._symbol_exposure.get(symbol, 0.0) + volume_lots

    def record_trade_close(
        self,
        timestamp: datetime,
        symbol: str,
        volume_lots: float,
        net_pnl: float,
    ) -> None:
        """Apply a completed trade and update loss-period protections."""
        if volume_lots <= 0:
            raise ValueError("volume_lots must be positive")
        current = _as_utc(timestamp)
        self._roll_periods(current)
        exposure = self._symbol_exposure.get(symbol, 0.0)
        if self._open_positions <= 0 or exposure + 1e-12 < volume_lots:
            raise RiskStateError("cannot close a position that is not tracked as open")
        remaining = exposure - volume_lots
        if isclose(remaining, 0.0, abs_tol=1e-12):
            self._symbol_exposure.pop(symbol, None)
        else:
            self._symbol_exposure[symbol] = remaining
        self._open_positions -= 1
        self.balance += net_pnl
        day, week = current.date(), _week_key(current)
        self._daily_realized_pnl[day] = self._daily_realized_pnl.get(day, 0.0) + net_pnl
        self._weekly_realized_pnl[week] = self._weekly_realized_pnl.get(week, 0.0) + net_pnl
        self.consecutive_losses = self.consecutive_losses + 1 if net_pnl < 0 else 0
        self.peak_equity = max(self.peak_equity, self.balance)

    def _roll_periods(self, timestamp: datetime) -> None:
        day, week = timestamp.date(), _week_key(timestamp)
        if (
            self._active_loss_day != day
            and self.reset_consecutive_losses_each_utc_day
        ):
            self.consecutive_losses = 0
            self._active_loss_day = day
        self._daily_realized_pnl.setdefault(day, 0.0)
        self._weekly_realized_pnl.setdefault(week, 0.0)
        self._daily_starting_equity.setdefault(day, self.balance)
        self._weekly_starting_equity.setdefault(week, self.balance)


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("risk-state timestamps must be timezone-aware")
    return timestamp.astimezone(UTC)


def _week_key(timestamp: datetime) -> tuple[int, int]:
    calendar = timestamp.isocalendar()
    return calendar.year, calendar.week


def _hour_key(timestamp: datetime) -> datetime:
    return timestamp.replace(minute=0, second=0, microsecond=0)
