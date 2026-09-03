"""Download a reproducible multi-year M1 research archive from HistData."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from collections.abc import Sequence

from mt5_scalping_agent.data import HistDataError, HistDataM1Client

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download read-only HistData annual bid-side M1 archives.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "histdata")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.start_year > args.end_year:
        raise ValueError("start year must not be after end year")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = HistDataM1Client()
    files: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for year in range(args.start_year, args.end_year + 1):
        path = args.output_dir / f"{args.symbol}_m1_{year}.csv.gz"
        if path.exists():
            print(f"{path.name}: exists, skipping")
            files.append({"path": str(path), "year": year, "status": "existing"})
            continue
        try:
            frame = client.annual_ohlcv(args.symbol, year)
        except HistDataError as error:
            failures.append({"year": year, "error": str(error)})
            print(f"{year}: validation failed: {error}")
            break
        frame.to_csv(path, index=False, compression="gzip")
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
                "source": "HistData Generic ASCII M1 bid bars, fixed EST normalized to UTC",
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
