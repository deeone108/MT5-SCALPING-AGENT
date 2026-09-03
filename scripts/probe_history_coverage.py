"""Probe read-only MT5 M1 availability across years without downloading full history."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta
from collections.abc import Sequence

import MetaTrader5 as mt5

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError
from mt5_scalping_agent.data.historical_range import MT5HistoricalRangeClient

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MT5 M1 history coverage using one small sample per year.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start-year", type=int, default=2006)
    parser.add_argument("--end-year", type=int, default=datetime.now(UTC).year)
    return parser.parse_args(arguments)


def sample_day(year: int) -> datetime:
    value = datetime(year, 7, 1, tzinfo=UTC)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.start_year > args.end_year:
        raise ValueError("start year must not be after end year")

    client = MT5HistoricalRangeClient(load_settings(), mt5)
    try:
        status = client.connect()
        if not status.connected:
            raise MT5DataError("MT5 initialized but terminal information is unavailable")
        client.select_symbol(args.symbol)
        print(f"Connected to {status.terminal_name or 'MT5'} (build {status.terminal_version or 'unknown'})")
        for year in range(args.start_year, args.end_year + 1):
            start = sample_day(year)
            try:
                bars = client.historical_ohlcv_range(args.symbol, mt5.TIMEFRAME_M1, start, start + timedelta(days=1))
                print(f"{year}: {len(bars)} bars, {bars['time'].iloc[0].isoformat()} to {bars['time'].iloc[-1].isoformat()}")
            except MT5DataError:
                print(f"{year}: unavailable")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
