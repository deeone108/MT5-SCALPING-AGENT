"""Broker-aware instrument normalization for FX and XAUUSD.

This module is deliberately read-only. It converts MT5 symbol metadata into a
validated project representation used by deterministic risk and later
execution layers. It never submits orders.
"""

from __future__ import annotations

from math import isfinite
import re
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mt5_scalping_agent.risk import SymbolRiskSpec


class InstrumentMetadataError(ValueError):
    """Raised when a broker symbol cannot be resolved or validated safely."""


class InstrumentSpec(BaseModel):
    """Validated broker contract metadata for one canonical instrument."""

    model_config = ConfigDict(frozen=True)

    canonical_symbol: str = Field(min_length=1)
    broker_symbol: str = Field(min_length=1)
    digits: int = Field(ge=0)
    point: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    tick_value: float = Field(gt=0)
    contract_size: float = Field(gt=0)
    volume_min: float = Field(gt=0)
    volume_max: float = Field(gt=0)
    volume_step: float = Field(gt=0)
    stops_level_points: int = Field(ge=0)
    freeze_level_points: int = Field(ge=0)
    spread_points: float = Field(ge=0)
    trade_mode: int | str | None = None
    margin_initial: float | None = Field(default=None, ge=0)
    margin_maintenance: float | None = Field(default=None, ge=0)
    currency_base: str | None = None
    currency_profit: str | None = None
    currency_margin: str | None = None

    @model_validator(mode="after")
    def validate_volume_bounds(self) -> InstrumentSpec:
        if self.volume_min > self.volume_max:
            raise ValueError("volume_min must not exceed volume_max")
        return self

    def to_risk_spec(self) -> SymbolRiskSpec:
        """Return the exact broker values consumed by monetary-risk sizing."""
        return SymbolRiskSpec(
            symbol=self.broker_symbol,
            point=self.point,
            tick_size=self.tick_size,
            tick_value=self.tick_value,
            volume_min=self.volume_min,
            volume_max=self.volume_max,
            volume_step=self.volume_step,
        )

    @property
    def minimum_stop_distance(self) -> float:
        return self.stops_level_points * self.point

    @property
    def freeze_distance(self) -> float:
        return self.freeze_level_points * self.point


def resolve_broker_symbol(canonical_symbol: str, available_symbols: Iterable[str]) -> str:
    """Resolve one broker symbol without guessing through ambiguity.

    Exact case-insensitive matches win. Otherwise a single suffix/prefix-style
    broker decoration (for example XAUUSDm or XAUUSD.c) is accepted. Multiple
    decorated candidates fail closed.
    """
    canonical = canonical_symbol.strip().upper()
    if not canonical:
        raise InstrumentMetadataError("canonical symbol must not be empty")

    names = [str(name).strip() for name in available_symbols if str(name).strip()]
    exact = [name for name in names if name.upper() == canonical]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise InstrumentMetadataError(f"ambiguous exact symbol mapping for {canonical}")

    decorated: list[str] = []
    token = re.compile(rf"^{re.escape(canonical)}(?:[._-]?[A-Z0-9]+)$", re.IGNORECASE)
    for name in names:
        if token.fullmatch(name):
            decorated.append(name)

    if len(decorated) == 1:
        return decorated[0]
    if not decorated:
        raise InstrumentMetadataError(f"no broker symbol found for {canonical}")
    raise InstrumentMetadataError(
        f"ambiguous broker symbol mapping for {canonical}: {sorted(decorated)}"
    )


def instrument_spec_from_mt5(
    canonical_symbol: str,
    broker_symbol: str,
    symbol_info: dict[str, Any],
    tick: dict[str, Any],
) -> InstrumentSpec:
    """Build a validated InstrumentSpec from MT5 symbol/tick dictionaries."""

    def required_number(key: str, *, positive: bool = True) -> float:
        raw = symbol_info.get(key)
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise InstrumentMetadataError(f"missing or invalid MT5 field: {key}") from exc
        if not isfinite(value) or (positive and value <= 0):
            raise InstrumentMetadataError(f"missing or invalid MT5 field: {key}")
        return value

    def optional_nonnegative(key: str) -> float | None:
        raw = symbol_info.get(key)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise InstrumentMetadataError(f"invalid MT5 field: {key}") from exc
        if not isfinite(value) or value < 0:
            raise InstrumentMetadataError(f"invalid MT5 field: {key}")
        return value

    point = required_number("point")
    bid = _finite_positive_tick(tick, "bid")
    ask = _finite_positive_tick(tick, "ask")
    if ask < bid:
        raise InstrumentMetadataError("MT5 ask must not be below bid")

    digits_raw = symbol_info.get("digits")
    try:
        digits = int(digits_raw)
    except (TypeError, ValueError) as exc:
        raise InstrumentMetadataError("missing or invalid MT5 field: digits") from exc
    if digits < 0:
        raise InstrumentMetadataError("missing or invalid MT5 field: digits")

    def nonnegative_int(key: str) -> int:
        raw = symbol_info.get(key, 0)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise InstrumentMetadataError(f"invalid MT5 field: {key}") from exc
        if value < 0:
            raise InstrumentMetadataError(f"invalid MT5 field: {key}")
        return value

    spec = InstrumentSpec(
        canonical_symbol=canonical_symbol.strip().upper(),
        broker_symbol=broker_symbol,
        digits=digits,
        point=point,
        tick_size=required_number("trade_tick_size"),
        tick_value=required_number("trade_tick_value"),
        contract_size=required_number("trade_contract_size"),
        volume_min=required_number("volume_min"),
        volume_max=required_number("volume_max"),
        volume_step=required_number("volume_step"),
        stops_level_points=nonnegative_int("trade_stops_level"),
        freeze_level_points=nonnegative_int("trade_freeze_level"),
        spread_points=(ask - bid) / point,
        trade_mode=symbol_info.get("trade_mode"),
        margin_initial=optional_nonnegative("margin_initial"),
        margin_maintenance=optional_nonnegative("margin_maintenance"),
        currency_base=_optional_text(symbol_info.get("currency_base")),
        currency_profit=_optional_text(symbol_info.get("currency_profit")),
        currency_margin=_optional_text(symbol_info.get("currency_margin")),
    )
    return spec


def load_instrument_spec(client: Any, canonical_symbol: str) -> InstrumentSpec:
    """Resolve, select and validate one symbol through the read-only MT5 client."""
    names = [item["name"] for item in client.list_symbols() if item.get("name")]
    broker_symbol = resolve_broker_symbol(canonical_symbol, names)
    client.select_symbol(broker_symbol)
    info = client.symbol_information(broker_symbol)
    tick = client.tick(broker_symbol)
    return instrument_spec_from_mt5(canonical_symbol, broker_symbol, info, tick)


def _finite_positive_tick(tick: dict[str, Any], key: str) -> float:
    raw = tick.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise InstrumentMetadataError(f"missing or invalid MT5 tick field: {key}") from exc
    if not isfinite(value) or value <= 0:
        raise InstrumentMetadataError(f"missing or invalid MT5 tick field: {key}")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
