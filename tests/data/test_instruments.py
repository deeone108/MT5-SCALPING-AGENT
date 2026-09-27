from __future__ import annotations

from types import SimpleNamespace

import pytest

from mt5_scalping_agent.data import (
    InstrumentMetadataError,
    instrument_spec_from_mt5,
    load_instrument_spec,
    resolve_broker_symbol,
)


def xau_info(**overrides):
    base = {
        "name": "XAUUSDm",
        "digits": 2,
        "point": 0.01,
        "trade_tick_size": 0.01,
        "trade_tick_value": 1.0,
        "trade_contract_size": 100.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_stops_level": 50,
        "trade_freeze_level": 10,
        "trade_mode": 4,
        "margin_initial": 0.0,
        "margin_maintenance": 0.0,
        "currency_base": "XAU",
        "currency_profit": "USD",
        "currency_margin": "USD",
    }
    base.update(overrides)
    return base


def test_exact_symbol_wins_over_decorated_aliases():
    assert resolve_broker_symbol("XAUUSD", ["XAUUSDm", "XAUUSD", "XAUUSD.c"]) == "XAUUSD"


def test_single_broker_suffix_is_resolved_safely():
    assert resolve_broker_symbol("XAUUSD", ["EURUSD", "XAUUSDm", "GBPUSD"]) == "XAUUSDm"


def test_ambiguous_gold_aliases_fail_closed():
    with pytest.raises(InstrumentMetadataError, match="ambiguous broker symbol"):
        resolve_broker_symbol("XAUUSD", ["XAUUSDm", "XAUUSDc"])


def test_non_equivalent_gold_name_is_not_guessed():
    with pytest.raises(InstrumentMetadataError, match="no broker symbol"):
        resolve_broker_symbol("XAUUSD", ["GOLD", "EURUSD"])


def test_xauusd_metadata_normalizes_to_monetary_risk_spec():
    spec = instrument_spec_from_mt5(
        "XAUUSD",
        "XAUUSDm",
        xau_info(),
        {"bid": 2650.10, "ask": 2650.25},
    )

    assert spec.canonical_symbol == "XAUUSD"
    assert spec.broker_symbol == "XAUUSDm"
    assert spec.digits == 2
    assert spec.point == 0.01
    assert spec.tick_size == 0.01
    assert spec.tick_value == 1.0
    assert spec.contract_size == 100.0
    assert spec.spread_points == pytest.approx(15.0)
    assert spec.minimum_stop_distance == pytest.approx(0.50)
    assert spec.freeze_distance == pytest.approx(0.10)

    risk = spec.to_risk_spec()
    assert risk.symbol == "XAUUSDm"
    assert risk.tick_size == 0.01
    assert risk.tick_value == 1.0
    assert risk.volume_min == 0.01
    assert risk.volume_step == 0.01


@pytest.mark.parametrize(
    ("info", "tick", "message"),
    [
        (xau_info(trade_tick_value=0), {"bid": 2650.1, "ask": 2650.2}, "trade_tick_value"),
        (xau_info(point=0), {"bid": 2650.1, "ask": 2650.2}, "point"),
        (xau_info(volume_step=0), {"bid": 2650.1, "ask": 2650.2}, "volume_step"),
        (xau_info(), {"bid": float("nan"), "ask": 2650.2}, "bid"),
        (xau_info(), {"bid": 2650.2, "ask": 2650.1}, "ask must not be below bid"),
    ],
)
def test_invalid_broker_metadata_fails_closed(info, tick, message):
    with pytest.raises(InstrumentMetadataError, match=message):
        instrument_spec_from_mt5("XAUUSD", "XAUUSDm", info, tick)


class FakeClient:
    def __init__(self, symbols):
        self.symbols = symbols
        self.selected = []

    def list_symbols(self):
        return [{"name": name} for name in self.symbols]

    def select_symbol(self, symbol):
        self.selected.append(symbol)

    def symbol_information(self, symbol):
        return xau_info(name=symbol)

    def tick(self, symbol):
        return {"symbol": symbol, "bid": 2650.10, "ask": 2650.20}


def test_load_instrument_spec_resolves_selects_and_reads_exact_broker_symbol():
    client = FakeClient(["EURUSD", "XAUUSDm", "GBPUSD"])

    spec = load_instrument_spec(client, "XAUUSD")

    assert spec.broker_symbol == "XAUUSDm"
    assert client.selected == ["XAUUSDm"]


def test_load_instrument_spec_never_selects_ambiguous_symbol():
    client = FakeClient(["XAUUSDm", "XAUUSDc"])

    with pytest.raises(InstrumentMetadataError, match="ambiguous"):
        load_instrument_spec(client, "XAUUSD")

    assert client.selected == []
