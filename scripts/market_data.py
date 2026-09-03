"""Display recent read-only MT5 market data and basic indicators."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import MetaTrader5 as mt5
import pandas as pd

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError, MT5ReadOnlyClient
from mt5_scalping_agent.indicators import with_indicators

LOGGER = logging.getLogger(__name__)
DISPLAY_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
INDICATOR_COLUMNS = [
    "ema_9",
    "ema_21",
    "rsi_14",
    "atr_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "volatility_20",
]


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display recent M1 and M5 OHLCV bars from a running MT5 terminal."
    )
    parser.add_argument("--symbol", default="EURUSD", help="MT5 symbol to retrieve")
    parser.add_argument("--bars", default=100, type=int, help="Historical bars to request per timeframe")
    parser.add_argument("--display-bars", default=10, type=int, help="Latest bars to print per timeframe")
    return parser.parse_args(arguments)


def display_timeframe(
    client: MT5ReadOnlyClient,
    symbol: str,
    label: str,
    timeframe: int,
    bars: int,
    display_bars: int,
) -> None:
    frame = with_indicators(client.historical_ohlcv(symbol, timeframe, bars))
    columns = [column for column in DISPLAY_COLUMNS if column in frame.columns]
    latest = frame.iloc[-1]

    print(f"\n{symbol} {label} - latest {min(display_bars, len(frame))} bars (UTC)")
    print(frame[columns].tail(display_bars).to_string(index=False))
    print("Latest indicators")
    for column in INDICATOR_COLUMNS:
        value = latest[column]
        rendered = "unavailable (insufficient history)" if pd.isna(value) else f"{value:.8f}"
        print(f"  {column}: {rendered}")


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.bars <= 0 or args.display_bars <= 0:
        raise ValueError("--bars and --display-bars must be greater than zero")

    settings = load_settings()
    client = MT5ReadOnlyClient(settings, mt5)

    try:
        status = client.connect()
        if not status.connected:
            raise MT5DataError("MT5 initialized but terminal information is unavailable")

        client.select_symbol(args.symbol)
        print(f"Connected to {status.terminal_name or 'MT5'} (build {status.terminal_version or 'unknown'})")
        display_timeframe(client, args.symbol, "M1", mt5.TIMEFRAME_M1, args.bars, args.display_bars)
        display_timeframe(client, args.symbol, "M5", mt5.TIMEFRAME_M5, args.bars, args.display_bars)
        return 0
    except (MT5DataError, RuntimeError) as error:
        LOGGER.error("Market-data request failed: %s", error)
        return 1
    finally:
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
