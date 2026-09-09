"""Prepare or run the resumable read-only Phase 22 MT5 tick archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import MetaTrader5 as mt5

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data.mt5_client import MT5ReadOnlyClient
from mt5_scalping_agent.data.mt5_historical_ticks import acquire_next, build_manifest

DEFAULT_MANIFEST = Path("reports/phase22_data_build/mt5_historical_manifest.json")
DEFAULT_DATA_ROOT = Path("data/ticks")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="create the immutable 240-unit acquisition plan")
    action.add_argument("--next", action="store_true", help="download and validate one pending pair/month")
    action.add_argument("--bulk", action="store_true", help="continue synchronously until all units validate or one fails")
    action.add_argument("--status", action="store_true", help="show manifest counts without connecting to MT5")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    return parser.parse_args()


def status(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    print(f"source={manifest['source_provider']} units={len(manifest['units'])}")
    for value in ("VALIDATED", "PENDING", "FAILED"):
        print(f"{value}={sum(unit['status'] == value for unit in manifest['units'])}")


def main() -> int:
    args = parse_arguments()
    if args.prepare:
        if args.manifest.exists():
            raise FileExistsError(f"refusing to overwrite manifest: {args.manifest}")
        build_manifest(args.manifest, args.data_root.resolve())
        status(args.manifest)
        return 0
    if args.status:
        status(args.manifest)
        return 0
    if not args.manifest.is_file():
        raise FileNotFoundError(f"prepare the manifest first: {args.manifest}")

    client = MT5ReadOnlyClient(load_settings(), mt5)
    try:
        connection = client.connect()
        print(f"CONNECTED={connection.connected} TERMINAL={connection.terminal_name}")
        while True:
            unit = acquire_next(client, args.manifest, mt5)
            if unit is None:
                print("PHASE22_MT5_ARCHIVE_COMPLETE")
                break
            print(
                f"VALIDATED {unit['pair']} {unit['year']}-{unit['month']:02d} "
                f"ticks={unit['tick_count']} raw_sha256={unit['raw_sha256']}"
            )
            if args.next:
                break
        status(args.manifest)
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())