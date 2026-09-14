from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from types import SimpleNamespace

import pandas as pd
import pytest

from mt5_scalping_agent.domain import TradeDirection
from mt5_scalping_agent.strategies.xau60 import (
    CRTTBSAdapter,
    SMCScalperAdapter,
    TrendBreakTraumaAdapter,
    XAU60_PIN,
    XAU60_SOURCE_ROOT_SHA256,
)
from mt5_scalping_agent.strategies.xau60.adapters import XAU60InputError


class _Signal(Enum):
    BUY = 1
    SELL = -1
    HOLD = 0


class RecordingUpstream:
    def __init__(self, signal=None):
        self.signal = signal
        self.config = None
        self.frames = []

    def initialize(self, config):
        self.config = config

    def analyze(self, symbol, frame):
        self.frames.append((symbol, frame.copy()))
        return self.signal


def bars(periods: int, interval: timedelta, *, spread: bool = True) -> pd.DataFrame:
    frame = pd.DataFrame({
        "time": pd.date_range("2026-01-05", periods=periods, freq=interval, tz=UTC),
        "open": [2000.0] * periods,
        "high": [2001.0] * periods,
        "low": [1999.0] * periods,
        "close": [2000.0] * periods,
        "volume": [100.0] * periods,
    })
    if spread:
        frame["spread"] = 2.0
    return frame


@pytest.mark.parametrize(
    ("adapter_type", "interval", "minimum", "timeframe"),
    [
        (SMCScalperAdapter, timedelta(minutes=15), 50, "M15"),
        (TrendBreakTraumaAdapter, timedelta(hours=1), 50, "H1"),
        (CRTTBSAdapter, timedelta(minutes=5), 6, "M5"),
    ],
)
def test_pinned_provenance_defaults_and_deterministic_no_signal(adapter_type, interval, minimum, timeframe):
    upstream = RecordingUpstream()
    adapter = adapter_type(upstream=upstream)
    frame = bars(minimum, interval)
    observed = frame.time.iloc[-1].to_pydatetime() + interval

    first = adapter.propose("XAUUSD", frame, observed)
    second = adapter.propose("XAUUSD", frame, observed)

    assert first == second
    assert first.direction is TradeDirection.NO_TRADE
    assert adapter.timeframe == timeframe
    assert upstream.config == adapter.default_config
    assert upstream.config is not adapter.default_config
    assert adapter.provenance() == {
        "upstream_commit": XAU60_PIN,
        "source_root_sha256": XAU60_SOURCE_ROOT_SHA256,
        "upstream_module": adapter.module,
        "upstream_class": adapter.class_name,
    }


@pytest.mark.parametrize(
    ("adapter_type", "interval", "minimum", "direction", "entry", "stop", "target"),
    [
        (SMCScalperAdapter, timedelta(minutes=15), 50, _Signal.BUY, 2000, 1990, 2020),
        (TrendBreakTraumaAdapter, timedelta(hours=1), 50, _Signal.SELL, 2000, 2010, 1980),
        (CRTTBSAdapter, timedelta(minutes=5), 6, _Signal.BUY, 2000, 1990, 2020),
    ],
)
def test_exact_upstream_signal_fields_translate_without_repricing(
    adapter_type, interval, minimum, direction, entry, stop, target
):
    signal = SimpleNamespace(
        signal=direction, symbol="XAUUSD", entry_price=entry,
        stop_loss=stop, take_profit=target, comment="UPSTREAM_COMMENT",
    )
    adapter = adapter_type(upstream=RecordingUpstream(signal))
    frame = bars(minimum, interval)
    result = adapter.propose("XAUUSD", frame, frame.time.iloc[-1].to_pydatetime() + interval)
    assert result.direction.name == direction.name
    assert (result.entry_price, result.stop_loss, result.take_profit) == (entry, stop, target)
    assert result.reasons == ("UPSTREAM_COMMENT",)


@pytest.mark.parametrize(
    ("adapter_type", "interval", "minimum"),
    [(SMCScalperAdapter, timedelta(minutes=15), 50),
     (TrendBreakTraumaAdapter, timedelta(hours=1), 50),
     (CRTTBSAdapter, timedelta(minutes=5), 6)],
)
def test_incomplete_latest_bar_is_never_exposed(adapter_type, interval, minimum):
    upstream = RecordingUpstream()
    adapter = adapter_type(upstream=upstream)
    frame = bars(minimum, interval)
    with pytest.raises(XAU60InputError, match="not completed"):
        adapter.propose("XAUUSD", frame, frame.time.iloc[-1].to_pydatetime())
    assert upstream.frames == []


@pytest.mark.parametrize("mutation, message", [
    (lambda f: f.drop(columns="close"), "missing required"),
    (lambda f: f.assign(close=float("nan")), "finite"),
    (lambda f: pd.concat([f.iloc[:-1], f.iloc[[-2]]], ignore_index=True), "unique and increasing"),
    (lambda f: f.assign(high=1990.0), "OHLCV"),
])
def test_invalid_schema_fails_closed(mutation, message):
    adapter = CRTTBSAdapter(upstream=RecordingUpstream())
    frame = mutation(bars(6, timedelta(minutes=5)))
    with pytest.raises(XAU60InputError, match=message):
        adapter.propose("XAUUSD", frame, datetime(2026, 1, 6, tzinfo=UTC))


def test_timezone_symbol_cadence_and_warmup_fail_closed():
    adapter = SMCScalperAdapter(upstream=RecordingUpstream())
    frame = bars(49, timedelta(minutes=15))
    observed = frame.time.iloc[-1].to_pydatetime() + timedelta(minutes=15)
    assert adapter.propose("XAUUSD", frame, observed).direction is TradeDirection.NO_TRADE
    with pytest.raises(XAU60InputError, match="exactly XAUUSD"):
        adapter.propose("EURUSD", frame, observed)
    with pytest.raises(XAU60InputError, match="timezone-aware"):
        adapter.propose("XAUUSD", frame, observed.replace(tzinfo=None))
    broken = frame.copy()
    broken.loc[10:, "time"] += timedelta(minutes=1)
    with pytest.raises(XAU60InputError, match="exact M15 cadence"):
        adapter.propose("XAUUSD", broken, observed + timedelta(minutes=1))


def test_adapters_are_exactly_the_three_authorized_classes():
    import mt5_scalping_agent.strategies.xau60 as package
    exported = {name for name in package.__all__ if name.endswith("Adapter")}
    assert exported == {"SMCScalperAdapter", "TrendBreakTraumaAdapter", "CRTTBSAdapter"}
