"""Download public Dukascopy M1 history as resumable, compressed local chunks."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Sequence

from mt5_scalping_agent.data import DukascopyM1Client

LOGGER = logging.getLogger(__name__)


def parse_utc_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset or Z suffix")
    return timestamp.astimezone(UTC)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download read-only Dukascopy bid-side M1 history in bounded chunks.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", required=True, help="Inclusive UTC ISO timestamp")
    parser.add_argument("--end", required=True, help="Exclusive UTC ISO timestamp")
    parser.add_argument("--chunk-days", type=int, default=14)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "dukascopy")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    start, end = parse_utc_timestamp(args.start), parse_utc_timestamp(args.end)
    client = DukascopyM1Client()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, object]] = []
    for chunk in client.iter_historical_ohlcv(args.symbol, start, end, args.chunk_days):
        chunk_start = chunk["time"].iloc[0].to_pydatetime()
        chunk_end = chunk["time"].iloc[-1].to_pydatetime()
        filename = f"{args.symbol}_m1_{chunk_start:%Y%m%d}_{chunk_end:%Y%m%d}.csv.gz"
        path = args.output_dir / filename
        if not path.exists():
            chunk.to_csv(path, index=False, compression="gzip")
        files.append(
            {
                "path": str(path),
                "rows": len(chunk),
                "first_time": chunk_start.isoformat(),
                "last_time": chunk_end.isoformat(),
            }
        )
        print(f"{filename}: {len(chunk)} bars")
    manifest = {
        "source": "Dukascopy public bid-side M1 feed",
        "symbol": args.symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "chunk_days": args.chunk_days,
        "files": files,
    }
    manifest_path = args.output_dir / f"{args.symbol}_m1_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())

