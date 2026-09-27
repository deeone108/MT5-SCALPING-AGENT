from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from enum import Enum
from importlib import import_module
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
from mt5_scalping_agent.strategies.xau60.adapters import XAU60InputError, _load_upstream


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


def bars(
    periods: int,
    interval: timedelta,
    *,
    spread: bool = True,
    start: str = "2026-01-05T00:00:00Z",
) -> pd.DataFrame:
    frame = pd.DataFrame({
        "time": pd.date_range(start, periods=periods, freq=interval, tz=UTC),
        "open": [2000.0] * periods,
        "high": [2001.0] * periods,
        "low": [1999.0] * periods,
        "close": [2000.0] * periods,
        "volume": [100.0] * periods,
    })
    if spread:
        frame["spread"] = 2.0
    return frame


CASES = [
    (SMCScalperAdapter, timedelta(minutes=15), 50, "M15"),
    (TrendBreakTraumaAdapter, timedelta(hours=1), 50, "H1"),
    (CRTTBSAdapter, timedelta(minutes=5), 20, "M5"),
]


@pytest.mark.parametrize(("adapter_type", "interval", "minimum", "timeframe"), CASES)
def test_pinned_provenance_defaults_and_deterministic_no_signal(
    adapter_type, interval, minimum, timeframe
):
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


@pytest.mark.parametrize(("adapter_type", "interval", "minimum", "timeframe"), CASES)
def test_real_pinned_default_construction_and_no_signal_parity(
    adapter_type, interval, minimum, timeframe
):
    direct_cls = _load_upstream(adapter_type.module, adapter_type.class_name)
    direct = direct_cls()
    direct.initialize(deepcopy(adapter_type.default_config))
    adapter = adapter_type()

    frame = bars(minimum, interval)
    observed = frame.time.iloc[-1].to_pydatetime() + interval
    direct_signal = direct.analyze("XAUUSD", frame.copy())
    proposal = adapter.propose("XAUUSD", frame.copy(), observed)

    assert adapter._upstream.__class__ is direct.__class__
    assert adapter._upstream.config == direct.config == adapter_type.default_config
    assert getattr(adapter._upstream, "timeframe") == getattr(direct, "timeframe") == timeframe
    assert direct_signal is None
    assert proposal.direction is TradeDirection.NO_TRADE


@pytest.mark.parametrize(("adapter_type", "interval", "minimum", "_timeframe"), CASES)
def test_real_pinned_fresh_instance_replay_is_deterministic(
    adapter_type, interval, minimum, _timeframe
):
    frame = bars(minimum, interval)
    observed = frame.time.iloc[-1].to_pydatetime() + interval

    first = adapter_type().propose("XAUUSD", frame.copy(), observed)
    second = adapter_type().propose("XAUUSD", frame.copy(), observed)

    assert first == second


@pytest.mark.parametrize(
    ("adapter_type", "interval", "minimum", "direction", "entry", "stop", "target"),
    [
        (SMCScalperAdapter, timedelta(minutes=15), 50, _Signal.BUY, 2000, 1990, 2020),
        (TrendBreakTraumaAdapter, timedelta(hours=1), 50, _Signal.SELL, 2000, 2010, 1980),
        (CRTTBSAdapter, timedelta(minutes=5), 20, _Signal.BUY, 2000, 1990, 2020),
    ],
)
def test_exact_upstream_signal_fields_translate_without_repricing(
    adapter_type, interval, minimum, direction, entry, stop, target
):
    signal = SimpleNamespace(
        signal=direction,
        symbol="XAUUSD",
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        comment="UPSTREAM_COMMENT",
    )
    adapter = adapter_type(upstream=RecordingUpstream(signal))
    frame = bars(minimum, interval)
    result = adapter.propose("XAUUSD", frame, frame.time.iloc[-1].to_pydatetime() + interval)
    assert result.direction.name == direction.name
    assert (result.entry_price, result.stop_loss, result.take_profit) == (entry, stop, target)
    assert result.reasons == ("UPSTREAM_COMMENT",)


@pytest.mark.parametrize(("adapter_type", "interval", "minimum", "_timeframe"), CASES)
@pytest.mark.parametrize("direction_name", ["BUY", "SELL"])
def test_real_pinned_signal_translation_parity(
    adapter_type, interval, minimum, _timeframe, direction_name
):
    direct_cls = _load_upstream(adapter_type.module, adapter_type.class_name)
    direct = direct_cls()
    direct.initialize(deepcopy(adapter_type.default_config))
    wrapped = direct_cls()
    adapter = adapter_type(upstream=wrapped)

    core = import_module("core.strategy_base")
    signal_enum = getattr(core.Signal, direction_name)
    if direction_name == "BUY":
        entry, stop, target = 2000.0, 1990.0, 2020.0
    else:
        entry, stop, target = 2000.0, 2010.0, 1980.0
    pinned_signal = core.TradeSignal(
        signal=signal_enum,
        symbol="XAUUSD",
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        comment="PINNED_PARITY",
        magic_number=getattr(direct, "magic_number", 0),
    )
    direct.analyze = lambda symbol, frame: pinned_signal
    wrapped.analyze = lambda symbol, frame: pinned_signal

    frame = bars(minimum, interval)
    observed = frame.time.iloc[-1].to_pydatetime() + interval
    expected = direct.analyze("XAUUSD", frame.copy())
    actual = adapter.propose("XAUUSD", frame.copy(), observed)

    assert actual.symbol == expected.symbol
    assert actual.direction.name == expected.signal.name
    assert actual.entry_price == expected.entry_price
    assert actual.stop_loss == expected.stop_loss
    assert actual.take_profit == expected.take_profit
    assert actual.reasons == (expected.comment,)


def test_crt_real_pinned_session_state_parity():
    adapter = CRTTBSAdapter()
    direct_cls = _load_upstream(adapter.module, adapter.class_name)
    direct = direct_cls()
    direct.initialize(deepcopy(adapter.default_config))

    frame = bars(
        20,
        timedelta(minutes=5),
        start="2026-01-05T05:30:00Z",
    )
    observed = frame.time.iloc[-1].to_pydatetime() + timedelta(minutes=5)

    direct_result = direct.analyze("XAUUSD", frame.copy())
    adapter_result = adapter.propose("XAUUSD", frame.copy(), observed)

    assert direct_result is None
    assert adapter_result.direction is TradeDirection.NO_TRADE
    assert direct._daily_trade_count == adapter._upstream._daily_trade_count
    assert direct._trades_today == adapter._upstream._trades_today
    assert direct._last_trade_date == adapter._upstream._last_trade_date
    assert direct._current_asian_range == adapter._upstream._current_asian_range


@pytest.mark.parametrize(
    ("adapter_type", "interval", "minimum"),
    [
        (SMCScalperAdapter, timedelta(minutes=15), 50),
        (TrendBreakTraumaAdapter, timedelta(hours=1), 50),
        (CRTTBSAdapter, timedelta(minutes=5), 20),
    ],
)
def test_incomplete_latest_bar_is_never_exposed(adapter_type, interval, minimum):
    upstream = RecordingUpstream()
    adapter = adapter_type(upstream=upstream)
    frame = bars(minimum, interval)
    with pytest.raises(XAU60InputError, match="not completed"):
        adapter.propose("XAUUSD", frame, frame.time.iloc[-1].to_pydatetime())
    assert upstream.frames == []


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda f: f.drop(columns="close"), "missing required"),
        (lambda f: f.assign(close=float("nan")), "finite"),
        (
            lambda f: pd.concat([f.iloc[:-1], f.iloc[[-2]]], ignore_index=True),
            "unique and increasing",
        ),
        (lambda f: f.assign(high=1990.0), "OHLCV"),
    ],
)
def test_invalid_schema_fails_closed(mutation, message):
    adapter = CRTTBSAdapter(upstream=RecordingUpstream())
    frame = mutation(bars(6, timedelta(minutes=5)))
    with pytest.raises(XAU60InputError, match=message):
        adapter.propose("XAUUSD", frame, datetime(2026, 1, 6, tzinfo=UTC))


@pytest.mark.parametrize(
    "signal, message",
    [
        (
            SimpleNamespace(
                signal=_Signal.BUY,
                symbol="EURUSD",
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
                comment="WRONG_SYMBOL",
            ),
            "symbol mismatch",
        ),
        (
            SimpleNamespace(
                signal=SimpleNamespace(name="WAIT"),
                symbol="XAUUSD",
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
                comment="BAD_DIRECTION",
            ),
            "unsupported upstream direction",
        ),
        (
            SimpleNamespace(
                signal=_Signal.BUY,
                symbol="XAUUSD",
                entry_price=float("nan"),
                stop_loss=1990.0,
                take_profit=2020.0,
                comment="NAN",
            ),
            "invalid upstream entry_price",
        ),
        (
            SimpleNamespace(
                signal=_Signal.SELL,
                symbol="XAUUSD",
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
                comment="BAD_GEOMETRY",
            ),
            "SELL price geometry",
        ),
    ],
)
def test_malformed_upstream_outputs_fail_closed(signal, message):
    adapter = CRTTBSAdapter(upstream=RecordingUpstream(signal))
    frame = bars(20, timedelta(minutes=5))
    observed = frame.time.iloc[-1].to_pydatetime() + timedelta(minutes=5)

    with pytest.raises(XAU60InputError, match=message):
        adapter.propose("XAUUSD", frame, observed)


def test_missing_upstream_symbol_fails_closed():
    signal = SimpleNamespace(
        signal=_Signal.BUY,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        comment="MISSING_SYMBOL",
    )
    adapter = CRTTBSAdapter(upstream=RecordingUpstream(signal))
    frame = bars(20, timedelta(minutes=5))
    observed = frame.time.iloc[-1].to_pydatetime() + timedelta(minutes=5)

    with pytest.raises(XAU60InputError, match="symbol mismatch"):
        adapter.propose("XAUUSD", frame, observed)


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
