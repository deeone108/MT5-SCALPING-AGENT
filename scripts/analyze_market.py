"""Generate a read-only deterministic market proposal from MT5 data."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import MetaTrader5 as mt5

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError, MT5ReadOnlyClient
from mt5_scalping_agent.indicators import with_indicators
from mt5_scalping_agent.strategies import MarketAnalysisInput, TrendScalper

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produce a read-only M1/M5 strategy proposal.")
    parser.add_argument("--symbol", default="EURUSD", help="MT5 symbol to analyze")
    parser.add_argument("--bars", default=100, type=int, help="Historical bars per timeframe")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.bars < 35:
        raise ValueError("--bars must be at least 35 for MACD warm-up")

    client = MT5ReadOnlyClient(load_settings(), mt5)
    try:
        status = client.connect()
        if not status.connected:
            raise MT5DataError("MT5 initialized but terminal information is unavailable")

        client.select_symbol(args.symbol)
        symbol = client.symbol_information(args.symbol)
        tick = client.tick(args.symbol)
        m1 = with_indicators(client.historical_ohlcv(args.symbol, mt5.TIMEFRAME_M1, args.bars))
        m5 = with_indicators(client.historical_ohlcv(args.symbol, mt5.TIMEFRAME_M5, args.bars))
        proposal = TrendScalper().propose(
            MarketAnalysisInput(
                symbol=args.symbol,
                m1=m1,
                m5=m5,
                bid=float(tick["bid"]),
                ask=float(tick["ask"]),
                point=float(symbol["point"]),
                observed_at=datetime.now(UTC),
            )
        )
        print(f"Connected to {status.terminal_name or 'MT5'} (build {status.terminal_version or 'unknown'})")
        print(f"{proposal.direction}: {proposal.strategy}")
        print(f"Timestamp: {proposal.generated_at.isoformat()}")
        if proposal.entry_price is not None:
            print(f"Indicative entry price: {proposal.entry_price:.5f}")
            print(f"Stop loss: {proposal.stop_loss:.5f}")
            print(f"Take profit: {proposal.take_profit:.5f}")
            print(f"Stop loss: {proposal.stop_loss:.5f}")
            print(f"Take profit: {proposal.take_profit:.5f}")
        print("Reasons:")
        for reason in proposal.reasons:
            print(f"  - {reason}")
        return 0
    except (MT5DataError, RuntimeError, KeyError) as error:
        LOGGER.error("Market analysis failed: %s", error)
        return 1
    finally:
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())


