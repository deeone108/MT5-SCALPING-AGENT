from datetime import UTC, datetime

import csv

import pytest

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5ReadOnlyClient
from mt5_scalping_agent.data.tick_capture import TickCaptureError, TickSpreadRecorder
from tests.data.test_mt5_client import FakeMT5


def test_captures_normalized_tick_and_spread_points() -> None:
    terminal = FakeMT5()
    terminal.symbol_info_tick = lambda symbol: type("Tick", (), {"_asdict": lambda self: {"bid": 1.1, "ask": 1.1002, "time_msc": 1_700_000_000_123}})()
    recorder = TickSpreadRecorder(MT5ReadOnlyClient(load_settings({}), terminal))

    record = recorder.capture("EURUSD", observed_at=datetime(2025, 1, 1, tzinfo=UTC))

    assert record["symbol"] == "EURUSD"
    assert record["spread_points"] == pytest.approx(20.0)
    assert record["tick_time"] == "2023-11-14T22:13:20.123000+00:00"


def test_appends_one_header_and_multiple_tick_records(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ticks.csv"
    recorder = TickSpreadRecorder(MT5ReadOnlyClient(load_settings({}), FakeMT5()))
    record = {"observed_at": "2025-01-01T00:00:00+00:00", "tick_time": "2025-01-01T00:00:00+00:00", "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "spread_points": 10.0}

    recorder.append_csv(path, record)
    recorder.append_csv(path, record)

    with path.open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_rejects_inverted_bid_ask_tick() -> None:
    terminal = FakeMT5()
    terminal.symbol_info_tick = lambda symbol: type("Tick", (), {"_asdict": lambda self: {"bid": 1.2, "ask": 1.1, "time": 1_700_000_000}})()

    with pytest.raises(TickCaptureError, match="below bid"):
        TickSpreadRecorder(MT5ReadOnlyClient(load_settings({}), terminal)).capture("EURUSD")
