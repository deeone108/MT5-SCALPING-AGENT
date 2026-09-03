"""Download validated annual M1 research files from the public Dukascopy feed."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from collections.abc import Sequence

import pandas as pd

from mt5_scalping_agent.data import DukascopyDataError, DukascopyM1Client
from mt5_scalping_agent.data.validation import validate_ohlcv

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download read-only annual Dukascopy bid-side M1 files.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "dukascopy_annual")
    return parser.parse_args(arguments)


def annual_ohlcv(client: DukascopyM1Client, symbol: str, year: int) -> pd.DataFrame:
    start = pd.Timestamp(year, 1, 1, tz="UTC").to_pydatetime()
    end = pd.Timestamp(year + 1, 1, 1, tz="UTC").to_pydatetime()
    chunks = list(client.iter_historical_ohlcv(symbol, start, end, chunk_days=14))
    if not chunks:
        raise DukascopyDataError(f"No Dukascopy M1 chunks returned for {symbol} {year}")
    return validate_ohlcv(pd.concat(chunks, ignore_index=True))


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.start_year > args.end_year:
        raise ValueError("start year must not be after end year")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = DukascopyM1Client()
    files: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for year in range(args.start_year, args.end_year + 1):
        path = args.output_dir / f"{args.symbol}_m1_{year}.csv.gz"
        if path.exists():
            print(f"{path.name}: exists, skipping")
            files.append({"path": str(path), "year": year, "status": "existing"})
            continue
        try:
            frame = annual_ohlcv(client, args.symbol, year)
        except (DukascopyDataError, ValueError) as error:
            failures.append({"year": year, "error": str(error)})
            print(f"{year}: download failed: {error}")
            break
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            frame.to_csv(temporary, index=False, compression="gzip")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        files.append(
            {
                "path": str(path),
                "year": year,
                "rows": len(frame),
                "first_time": frame["time"].iloc[0].isoformat(),
                "last_time": frame["time"].iloc[-1].isoformat(),
            }
        )
        print(f"{path.name}: {len(frame)} bars")
    manifest_path = args.output_dir / f"{args.symbol}_m1_{args.start_year}_{args.end_year}_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source": "Dukascopy public bid-side M1 feed, UTC timestamps",
                "symbol": args.symbol,
                "start_year": args.start_year,
                "end_year": args.end_year,
                "files": files,
                "failures": failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Manifest: {manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
