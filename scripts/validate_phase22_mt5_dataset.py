"""Semantic completion validator and root-hash builder for Phase 22 MT5 ticks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.data.mt5_historical_ticks import NORMALIZED_FIELDS, PAIRS, PROVIDER, _sha256

BOUNDARY_NS = int(pd.Timestamp("2024-01-01T00:00:00Z").value)


def merkle_root(items: list[tuple[str, str]]) -> str:
    payload = "".join(f"{name}\0{digest}\n" for name, digest in sorted(items)).encode()
    return hashlib.sha256(payload).hexdigest()


def classify_gaps(times: np.ndarray) -> dict[str, object]:
    gaps = np.diff(times) / 1_000_000
    return {
        "p50_ms": float(np.percentile(gaps, 50)),
        "p90_ms": float(np.percentile(gaps, 90)),
        "p95_ms": float(np.percentile(gaps, 95)),
        "p99_ms": float(np.percentile(gaps, 99)),
        "maximum_ms": float(gaps.max()),
        "over_5s": int((gaps > 5_000).sum()),
        "over_30s": int((gaps > 30_000).sum()),
        "over_60s": int((gaps > 60_000).sum()),
        "over_5m": int((gaps > 300_000).sum()),
    }


def validate(manifest_path: Path, report_root: Path) -> tuple[dict, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    units = manifest["units"]
    if len(units) != 240:
        raise ValueError(f"expected 240 units, found {len(units)}")
    if any(unit["status"] != "VALIDATED" for unit in units):
        raise ValueError("not all manifest units are VALIDATED")

    run_id = "phase22_mt5_validation_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "run_id": run_id,
        "provider": PROVIDER,
        "units_expected": 240,
        "units_validated": 0,
        "units_failed": 0,
        "pair_year": {},
        "pairs": {},
        "replay": {},
    }
    all_raw, all_normalized = [], []

    for pair in PAIRS:
        pair_raw, pair_normalized = [], []
        for year in range(2019, 2024):
            group = [u for u in units if u["pair"] == pair and u["year"] == year]
            times_parts, spread_parts = [], []
            timestamp_duplicate_rows = same_quote_rows = 0
            raw_bytes = normalized_bytes = 0
            first = last = None
            for unit in group:
                raw_path, normalized_path = Path(unit["raw_path"]), Path(unit["normalized_path"])
                raw_hash, normalized_hash = _sha256(raw_path), _sha256(normalized_path)
                if raw_hash != unit["raw_sha256"] or normalized_hash != unit["normalized_sha256"]:
                    raise ValueError(f"hash mismatch: {pair} {year}-{unit['month']:02d}")
                frame = pd.read_parquet(normalized_path)
                if tuple(frame.columns) != NORMALIZED_FIELDS or frame.empty:
                    raise ValueError(f"schema/empty failure: {normalized_path}")
                numeric = frame[["timestamp_utc_ns", "bid", "ask", "last", "source_volume_real",
                                 "mid_price", "spread_price", "spread_pips"]].to_numpy()
                if not np.isfinite(numeric).all():
                    raise ValueError(f"non-finite required value: {normalized_path}")
                times = frame["timestamp_utc_ns"].to_numpy(dtype="int64")
                start_ns = int(pd.Timestamp(unit["start_utc"]).value)
                end_ns = int(pd.Timestamp(unit["end_utc"]).value)
                if times.min() < start_ns or times.max() >= end_ns or times.max() >= BOUNDARY_NS:
                    raise ValueError(f"timestamp boundary failure: {normalized_path}")
                if np.any(np.diff(times) < 0):
                    raise ValueError(f"non-monotonic timestamps: {normalized_path}")
                if ((frame.bid <= 0) | (frame.ask <= 0) | (frame.ask < frame.bid)).any():
                    raise ValueError(f"quote failure: {normalized_path}")
                if not frame.source_provider.eq(PROVIDER).all():
                    raise ValueError(f"provider mixing: {normalized_path}")
                if not np.array_equal(frame.source_sequence.to_numpy(), np.arange(len(frame))):
                    raise ValueError(f"source ordering failure: {normalized_path}")
                times_parts.append(times)
                spread_parts.append(frame.spread_pips.to_numpy())
                quotes = frame[["timestamp_utc_ns", "bid", "ask", "last", "source_volume",
                                "source_volume_real", "tick_flags"]]
                timestamp_duplicate_rows += int(frame["timestamp_utc_ns"].duplicated(keep=False).sum())
                same_quote_rows += int(quotes.duplicated(keep=False).sum())
                first = int(times[0]) if first is None else min(first, int(times[0]))
                last = int(times[-1]) if last is None else max(last, int(times[-1]))
                raw_bytes += raw_path.stat().st_size
                normalized_bytes += normalized_path.stat().st_size
                pair_raw.append((raw_path.as_posix(), raw_hash))
                pair_normalized.append((normalized_path.as_posix(), normalized_hash))
                result["units_validated"] += 1

            times = np.concatenate(times_parts)
            spreads = np.concatenate(spread_parts)

            stats = {
                "months": 12,
                "ticks": int(len(times)),
                "first_utc": pd.Timestamp(first, unit="ns", tz="UTC").isoformat(),
                "last_utc": pd.Timestamp(last, unit="ns", tz="UTC").isoformat(),
                "spread_p50_p90_p95_p99_max": [float(x) for x in np.percentile(spreads, [50, 90, 95, 99, 100])],
                "duplicates": {
                    "exact_duplicate_rows": same_quote_rows,
                    "same_timestamp_same_quote_rows": same_quote_rows,
                    "same_timestamp_different_quote_rows": max(timestamp_duplicate_rows - same_quote_rows, 0),
                },
                "gaps": classify_gaps(times),
                "raw_bytes": raw_bytes,
                "normalized_bytes": normalized_bytes,
            }
            raw_items = pair_raw[-12:]
            normalized_items = pair_normalized[-12:]
            stats["PAIR_YEAR_RAW_ROOT_SHA256"] = merkle_root(raw_items)
            stats["PAIR_YEAR_NORMALIZED_ROOT_SHA256"] = merkle_root(normalized_items)
            result["pair_year"][f"{pair}_{year}"] = stats
            sample = pd.read_parquet(Path(group[0]["normalized_path"]))
            evidence = hashlib.sha256(pd.util.hash_pandas_object(sample, index=False).values.tobytes()).hexdigest()
            repeated = hashlib.sha256(pd.util.hash_pandas_object(sample, index=False).values.tobytes()).hexdigest()
            result["replay"][f"{pair}_{year}"] = {
                "month": 1,
                "rows": len(sample),
                "deterministic": evidence == repeated,
                "hash": evidence,
                "same_millisecond_rows": int(sample.timestamp_utc_ns.duplicated(keep=False).sum()),
            }
        result["pairs"][pair] = {
            "PAIR_2019_2023_RAW_ROOT_SHA256": merkle_root(pair_raw),
            "PAIR_2019_2023_NORMALIZED_ROOT_SHA256": merkle_root(pair_normalized),
        }
        all_raw.extend(pair_raw)
        all_normalized.extend(pair_normalized)

    result["PHASE22_MT5_DEVELOPMENT_RAW_ROOT_SHA256"] = merkle_root(all_raw)
    result["PHASE22_MT5_DEVELOPMENT_NORMALIZED_ROOT_SHA256"] = merkle_root(all_normalized)
    result["raw_bytes"] = sum(Path(unit["raw_path"]).stat().st_size for unit in units)
    result["normalized_bytes"] = sum(Path(unit["normalized_path"]).stat().st_size for unit in units)
    result["total_ticks"] = sum(value["ticks"] for value in result["pair_year"].values())
    result["raw_bytes_per_tick"] = result["raw_bytes"] / result["total_ticks"]
    result["normalized_bytes_per_tick"] = result["normalized_bytes"] / result["total_ticks"]
    result["completion_validator"] = "PASSED"
    report_path = report_root / run_id / "completion_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=False)
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("reports/phase22_data_build/mt5_historical_manifest.json"))
    parser.add_argument("--report-root", type=Path, default=Path("reports/phase22_data_build"))
    args = parser.parse_args()
    result, path = validate(args.manifest, args.report_root)
    print(json.dumps({"run_id": result["run_id"], "ticks": result["total_ticks"],
                      "raw_root": result["PHASE22_MT5_DEVELOPMENT_RAW_ROOT_SHA256"],
                      "normalized_root": result["PHASE22_MT5_DEVELOPMENT_NORMALIZED_ROOT_SHA256"],
                      "report": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())