"""Typed data exchanged between deterministic strategy components."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TradeDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class SignalProposal(BaseModel):
    """A strategy opinion only; it has no execution authority."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    direction: TradeDirection
    strategy: str = Field(min_length=1)
    generated_at: datetime
    entry_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_trade_geometry(self) -> SignalProposal:
        if self.direction is TradeDirection.NO_TRADE:
            if any(value is not None for value in (self.entry_price, self.stop_loss, self.take_profit)):
                raise ValueError("NO_TRADE proposals cannot include trade prices")
            return self
        if any(value is None for value in (self.entry_price, self.stop_loss, self.take_profit)):
            raise ValueError("BUY and SELL proposals require entry, stop loss, and take profit")
        if self.direction is TradeDirection.BUY and not self.stop_loss < self.entry_price < self.take_profit:
            raise ValueError("BUY proposal requires stop_loss < entry_price < take_profit")
        if self.direction is TradeDirection.SELL and not self.take_profit < self.entry_price < self.stop_loss:
            raise ValueError("SELL proposal requires take_profit < entry_price < stop_loss")
        return self
