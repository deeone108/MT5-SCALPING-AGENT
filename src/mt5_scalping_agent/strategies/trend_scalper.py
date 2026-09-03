"""Deterministic M1/M5 trend proposal strategy for research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mt5_scalping_agent.domain import SignalProposal, TradeDirection


class TrendScalperConfig(BaseModel):
    """Research defaults that must be validated in backtests before use."""

    model_config = ConfigDict(frozen=True)

    max_spread_points: float = Field(default=3.0, gt=0)
    max_m1_age: timedelta = timedelta(minutes=5)
    max_m5_age: timedelta = timedelta(minutes=15)
    session_start_utc: time = time(hour=7)
    session_end_utc: time = time(hour=20)
    buy_rsi_minimum: float = Field(default=52.0, ge=0, le=100)
    buy_rsi_maximum: float = Field(default=70.0, ge=0, le=100)
    sell_rsi_minimum: float = Field(default=30.0, ge=0, le=100)
    sell_rsi_maximum: float = Field(default=48.0, ge=0, le=100)
    stop_loss_atr_multiple: float = Field(default=1.0, gt=0)
    take_profit_atr_multiple: float = Field(default=2.0, gt=0)
    min_m5_trend_strength: float = Field(default=0.0, ge=0)
    min_m1_atr_fraction: float = Field(default=0.0, ge=0)
    require_m1_pullback: bool = False

    @model_validator(mode="after")
    def validate_rsi_ranges(self) -> TrendScalperConfig:
        if self.buy_rsi_minimum > self.buy_rsi_maximum:
            raise ValueError("buy RSI minimum must not exceed its maximum")
        if self.sell_rsi_minimum > self.sell_rsi_maximum:
            raise ValueError("sell RSI minimum must not exceed its maximum")
        if self.max_m1_age <= timedelta(0) or self.max_m5_age <= timedelta(0):
            raise ValueError("maximum candle ages must be positive")
        return self


@dataclass(frozen=True)
class MarketAnalysisInput:
    symbol: str
    m1: pd.DataFrame
    m5: pd.DataFrame
    bid: float
    ask: float
    point: float
    observed_at: datetime

    @property
    def spread_points(self) -> float:
        if self.point <= 0:
            raise ValueError("point must be greater than zero")
        return (self.ask - self.bid) / self.point


class TrendScalper:
    """Propose trades only when both timeframes meet deterministic conditions."""

    name = "m1_m5_trend_scalper_v1"
    _required_indicators = frozenset({"time", "close", "ema_9", "ema_21", "rsi_14", "atr_14", "macd", "macd_signal"})

    def __init__(self, config: TrendScalperConfig | None = None) -> None:
        self._config = config or TrendScalperConfig()

    @property
    def required_m1_bars(self) -> int:
        return 2 if self._config.require_m1_pullback else 1

    def propose(self, market: MarketAnalysisInput) -> SignalProposal:
        """Return a proposal with rejection reasons; never contact an execution system."""
        now = _as_utc(market.observed_at)
        reasons = self._preconditions(market, now)
        if reasons:
            return self._no_trade(market.symbol, now, reasons)

        m1 = market.m1.iloc[-1]
        m5 = market.m5.iloc[-1]
        previous_m1 = market.m1.iloc[-2] if self._config.require_m1_pullback else None
        pullback_buy = previous_m1 is None or (
            previous_m1["close"] <= previous_m1["ema_9"] and m1["close"] > m1["ema_9"]
        )
        pullback_sell = previous_m1 is None or (
            previous_m1["close"] >= previous_m1["ema_9"] and m1["close"] < m1["ema_9"]
        )
        buy = (
            m1["ema_9"] > m1["ema_21"]
            and m5["ema_9"] > m5["ema_21"]
            and m1["macd"] > m1["macd_signal"]
            and self._config.buy_rsi_minimum <= m1["rsi_14"] <= self._config.buy_rsi_maximum
            and pullback_buy
        )
        sell = (
            m1["ema_9"] < m1["ema_21"]
            and m5["ema_9"] < m5["ema_21"]
            and m1["macd"] < m1["macd_signal"]
            and self._config.sell_rsi_minimum <= m1["rsi_14"] <= self._config.sell_rsi_maximum
            and pullback_sell
        )
        atr = float(m1["atr_14"])

        if buy:
            return self._proposal(market.symbol, TradeDirection.BUY, float(market.ask), atr, now, "M1/M5 uptrend with bullish momentum")
        if sell:
            return self._proposal(market.symbol, TradeDirection.SELL, float(market.bid), atr, now, "M1/M5 downtrend with bearish momentum")
        return self._no_trade(market.symbol, now, ["trend and momentum conditions are not aligned"])

    def _preconditions(self, market: MarketAnalysisInput, now: datetime) -> list[str]:
        if not market.symbol.strip():
            return ["symbol is empty"]
        if not self._in_session(now.time()):
            return ["outside configured trading session"]
        if market.spread_points > self._config.max_spread_points:
            return [f"spread {market.spread_points:.2f} points exceeds limit {self._config.max_spread_points:.2f}"]

        reasons: list[str] = []
        for label, frame, maximum_age in (("M1", market.m1, self._config.max_m1_age), ("M5", market.m5, self._config.max_m5_age)):
            missing = self._required_indicators.difference(frame.columns)
            if missing or frame.empty:
                reasons.append(f"{label} indicator data is incomplete")
                continue
            latest = frame.iloc[-1]
            if latest[list(self._required_indicators)].isna().any():
                reasons.append(f"{label} indicator warm-up is incomplete")
                continue
            candle_time = _as_utc(latest["time"].to_pydatetime())
            if now - candle_time > maximum_age:
                reasons.append(f"{label} data is stale")
        if not reasons and self._config.require_m1_pullback:
            if len(market.m1) < 2:
                reasons.append("M1 pullback entry requires two completed candles")
            elif market.m1.iloc[-2][list(self._required_indicators)].isna().any():
                reasons.append("M1 pullback indicator warm-up is incomplete")

        if not reasons and self._config.min_m5_trend_strength > 0:
            m5 = market.m5.iloc[-1]
            atr = float(m5["atr_14"])
            strength = abs(float(m5["ema_9"]) - float(m5["ema_21"])) / atr if atr > 0 else 0.0
            if strength < self._config.min_m5_trend_strength:
                reasons.append(
                    f"M5 trend strength {strength:.3f} is below limit {self._config.min_m5_trend_strength:.3f}"
                )
        if not reasons and self._config.min_m1_atr_fraction > 0:
            m1 = market.m1.iloc[-1]
            atr_fraction = float(m1["atr_14"]) / float(m1["close"])
            if atr_fraction < self._config.min_m1_atr_fraction:
                reasons.append(
                    f"M1 ATR fraction {atr_fraction:.6f} is below limit {self._config.min_m1_atr_fraction:.6f}"
                )
        return reasons

    def _in_session(self, current: time) -> bool:
        start, end = self._config.session_start_utc, self._config.session_end_utc
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    def _proposal(self, symbol: str, direction: TradeDirection, entry_price: float, atr: float, now: datetime, reason: str) -> SignalProposal:
        if direction is TradeDirection.BUY:
            stop_loss = entry_price - atr * self._config.stop_loss_atr_multiple
            take_profit = entry_price + atr * self._config.take_profit_atr_multiple
        else:
            stop_loss = entry_price + atr * self._config.stop_loss_atr_multiple
            take_profit = entry_price - atr * self._config.take_profit_atr_multiple
        return SignalProposal(symbol=symbol, direction=direction, strategy=self.name, generated_at=now, entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit, reasons=(reason,))

    def _no_trade(self, symbol: str, now: datetime, reasons: list[str]) -> SignalProposal:
        return SignalProposal(symbol=symbol, direction=TradeDirection.NO_TRADE, strategy=self.name, generated_at=now, reasons=tuple(reasons))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)




