"""Build resumable Phase 22A anchor partitions without crossing temporal gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from mt5_scalping_agent.research.phase22a_microstructure import build_anchor_table

DATASET_ROOT = "ae0f5b70f686c1b0fff05c0b71f9efb7c3d5da4983eba0df895989dbf6572a91"
SPEC_HASH = "11581b33dcd0616d25ad39cc2de37db6e4bbba62e49ea1d283b1a3449d988323"
YEARS = {"DISCOVERY": {2019, 2020, 2021}, "CONFIRMATION": {2022}, "INTERNAL_HOLDOUT": {2023}}
COLUMNS = ["timestamp_utc_ns", "bid", "ask"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=tuple(YEARS), required=True)
    parser.add_argument("--run-id", default="phase22a_20260909T220000Z")
    parser.add_argument("--manifest", type=Path, default=Path("reports/phase22_data_build/mt5_historical_manifest.json"))
    parser.add_argument("--report-root", type=Path, default=Path("reports/phase22a"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    units = [u for u in manifest["units"] if u["year"] in YEARS[args.partition]]
    run = args.report_root / args.run_id
    output_root = run / "anchors" / args.partition.lower()
    progress_path = run / f"{args.partition.lower()}_anchor_manifest.json"
    progress = {
        "run_id": args.run_id,
        "partition": args.partition,
        "dataset_root": DATASET_ROOT,
        "spec_sha256": SPEC_HASH,
        "units_expected": len(units),
        "units": {},
    }
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))

    all_units = manifest["units"]
    for index, unit in enumerate(all_units):
        if unit["year"] not in YEARS[args.partition]:
            continue
        key = f"{unit['pair']}_{unit['year']}_{unit['month']:02d}"
        if progress["units"].get(key, {}).get("status") == "VALIDATED":
            continue
        context = []
        for offset in (-1, 0, 1):
            pos = index + offset
            if 0 <= pos < len(all_units) and all_units[pos]["pair"] == unit["pair"]:
                context.append(pd.read_parquet(all_units[pos]["normalized_path"], columns=COLUMNS))
        ticks = pd.concat(context, ignore_index=True).sort_values(
            "timestamp_utc_ns", kind="stable"
        ).reset_index(drop=True)
        start = pd.Timestamp(unit["start_utc"])
        end = pd.Timestamp(unit["end_utc"])
        anchors = build_anchor_table(ticks, unit["pair"], start, end)
        if (anchors["year"] != unit["year"]).any():
            raise ValueError(f"temporal partition leak in {key}")
        output = output_root / unit["pair"] / str(unit["year"]) / f"{unit['month']:02d}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"unmanifested anchor output exists: {output}")
        temporary = output.with_suffix(".parquet.part")
        anchors.to_parquet(temporary, index=False)
        os.replace(temporary, output)
        progress["units"][key] = {
            "status": "VALIDATED",
            "eligible_anchors": len(anchors),
            "sha256": sha256(output),
            "path": str(output),
        }
        progress["eligible_anchors"] = sum(v["eligible_anchors"] for v in progress["units"].values())
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        part = progress_path.with_suffix(".json.part")
        part.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        os.replace(part, progress_path)
        print(f"ANCHORS {key} {len(anchors)}", flush=True)
    print(json.dumps({"partition": args.partition, "units": len(progress["units"]),
                      "eligible_anchors": progress.get("eligible_anchors", 0)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())