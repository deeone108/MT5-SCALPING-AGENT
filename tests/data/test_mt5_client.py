from types import SimpleNamespace

import numpy as np
import pytest

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5ConnectionError, MT5DataError, MT5ReadOnlyClient


class FakeMT5:
    def __init__(self, *, initializes: bool = True) -> None:
        self.initializes = initializes
        self.initialize_options = None
        self.shutdown_calls = 0
        self.selected_symbols = []
        self.rates = np.array(
            [
                (1_700_000_060, 1.2, 1.3, 1.1, 1.25, 50),
                (1_700_000_000, 1.0, 1.2, 0.9, 1.1, 100),
            ],
            dtype=[
                ("time", "i8"),
                ("open", "f8"),
                ("high", "f8"),
                ("low", "f8"),
                ("close", "f8"),
                ("tick_volume", "i8"),
            ],
        )

    def initialize(self, **options):
        self.initialize_options = options
        return self.initializes

    def shutdown(self):
        self.shutdown_calls += 1

    def last_error(self):
        return (500, "test error")

    def terminal_info(self):
        return SimpleNamespace(name="MetaTrader 5", build="5000")

    def symbol_select(self, symbol, visible):
        self.selected_symbols.append((symbol, visible))
        return True

    def account_info(self):
        return SimpleNamespace(_asdict=lambda: {"login": 123, "equity": 1000.0})

    def symbol_info(self, symbol):
        return SimpleNamespace(_asdict=lambda: {"name": symbol, "point": 0.00001})

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(_asdict=lambda: {"symbol": symbol, "bid": 1.1, "ask": 1.2})

    def copy_rates_from_pos(self, symbol, timeframe, start, bars):
        return self.rates


def test_connect_passes_configured_connection_options() -> None:
    settings = load_settings(
        {
            "MT5_LOGIN": "123",
            "MT5_PASSWORD": "secret",
            "MT5_SERVER": "Broker-Demo",
            "MT5_PATH": "C:/MT5/terminal64.exe",
        }
    )
    terminal = FakeMT5()

    status = MT5ReadOnlyClient(settings, terminal).connect()

    assert status.connected is True
    assert terminal.initialize_options == {
        "path": str(settings.mt5_path),
        "login": 123,
        "password": "secret",
        "server": "Broker-Demo",
    }


def test_connect_raises_with_mt5_error() -> None:
    client = MT5ReadOnlyClient(load_settings({}), FakeMT5(initializes=False))

    with pytest.raises(MT5ConnectionError, match="initialization failed"):
        client.connect()


def test_disconnect_only_shuts_down_initialized_client() -> None:
    terminal = FakeMT5()
    client = MT5ReadOnlyClient(load_settings({}), terminal)

    client.disconnect()
    client.connect()
    client.disconnect()
    client.disconnect()

    assert terminal.shutdown_calls == 1


def test_reads_account_symbol_and_tick_data() -> None:
    terminal = FakeMT5()
    client = MT5ReadOnlyClient(load_settings({}), terminal)

    client.select_symbol("EURUSD")

    assert terminal.selected_symbols == [("EURUSD", True)]
    assert client.account_information()["equity"] == 1000.0
    assert client.symbol_information("EURUSD")["point"] == 0.00001
    assert client.tick("EURUSD")["ask"] == 1.2


def test_normalizes_and_sorts_historical_ohlcv() -> None:
    client = MT5ReadOnlyClient(load_settings({}), FakeMT5())

    bars = client.historical_ohlcv("EURUSD", timeframe=1, bars=2)

    assert bars["time"].dt.tz is not None
    assert bars["time"].is_monotonic_increasing
    assert list(bars["close"]) == [1.1, 1.25]


def test_rejects_empty_symbol_and_empty_historical_data() -> None:
    terminal = FakeMT5()
    client = MT5ReadOnlyClient(load_settings({}), terminal)

    with pytest.raises(ValueError, match="symbol"):
        client.tick("  ")

    terminal.rates = None
    with pytest.raises(MT5DataError, match="No historical rates"):
        client.historical_ohlcv("EURUSD", timeframe=1, bars=2)
