"""Capture read-only MT5 bid/ask ticks for broker-cost research."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from pathlib import Path

import MetaTrader5 as mt5

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5ConnectionError, MT5DataError, MT5ReadOnlyClient, TickSpreadRecorder

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record read-only MT5 bid/ask ticks to a local CSV file.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "mt5_ticks")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.samples <= 0 or args.interval_seconds < 0:
        raise ValueError("samples must be positive and interval-seconds cannot be negative")
    client = MT5ReadOnlyClient(load_settings(), mt5)
    try:
        status = client.connect()
        if not status.connected:
            raise MT5ConnectionError("MT5 initialized but terminal information is unavailable")
        recorder = TickSpreadRecorder(client)
        output_path = args.output_dir / f"{args.symbol.upper()}_ticks.csv"
        for index in range(args.samples):
            recorder.append_csv(output_path, recorder.capture(args.symbol))
            if index + 1 < args.samples:
                time.sleep(args.interval_seconds)
        print(f"Captured {args.samples} ticks from {status.terminal_name or 'MT5'}: {output_path}")
        return 0
    except (MT5ConnectionError, MT5DataError, ValueError) as error:
        LOGGER.error("Tick capture failed: %s", error)
        return 1
    finally:
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
