"""Evaluate frozen Phase 22A candidates one temporal partition at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from mt5_scalping_agent.research.phase22a_microstructure import (
    HORIZONS, LOOKBACKS, apply_frozen_bins, benjamini_hochberg,
    block_bootstrap, quantile_boundaries,
)

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
SPEC_HASH = "11581b33dcd0616d25ad39cc2de37db6e4bbba62e49ea1d283b1a3449d988323"

def json_default(value):
    """Convert NumPy scalars without altering calculated values."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def confidence_interval_excludes_zero(bootstrap: dict) -> bool:
    """Fail closed when inference cannot produce both confidence bounds."""
    low, high = bootstrap.get("ci_low"), bootstrap.get("ci_high")
    return low is not None and high is not None and (low > 0 or high < 0)


def candidates() -> list[dict]:
    out = []
    for w in LOOKBACKS:
        for h in HORIZONS:
            out.extend([
                {"id": f"P22A_QDI_{w}s_{h}s", "family": "QDI", "feature": f"qdi_{w}s", "h": h, "kind": "signed"},
                {"id": f"P22A_IMP_{w}s_{h}s", "family": "IMP", "feature": f"impulse_{w}s_pips", "h": h, "kind": "signed"},
                {"id": f"P22A_ACT_ABS_{w}s_{h}s", "family": "ACT_ABS", "feature": f"activity_{w}s", "h": h, "kind": "contrast_abs"},
                {"id": f"P22A_ACT_DIR_{w}s_{h}s", "family": "ACT_DIR", "feature": f"activity_{w}s", "direction": f"impulse_{w}s_pips", "h": h, "kind": "high_signed"},
                {"id": f"P22A_VOL_DIR_{w}s_{h}s", "family": "VOL_DIR", "feature": f"volatility_{w}s", "direction": f"impulse_{w}s_pips", "h": h, "kind": "high_signed"},
            ])
    for h in HORIZONS:
        out.extend([
            {"id": f"P22A_SPR_ABS_15s_{h}s", "family": "SPR_ABS", "feature": "spread_dislocation", "h": h, "kind": "contrast_abs"},
            {"id": f"P22A_SPR_NORM_15s_{h}s", "family": "SPR_NORM", "feature": "spread_dislocation", "h": h, "kind": "contrast_spread"},
        ])
    return out


def effect_rows(frame: pd.DataFrame, candidate: dict, boundaries: list[float]) -> pd.DataFrame:
    feature = frame[candidate["feature"]].to_numpy()
    bins = apply_frozen_bins(feature, boundaries)
    h = candidate["h"]
    future_spread = frame[f"future_change_{h}s_spread"].to_numpy()
    future_pips = frame[f"future_change_{h}s_pips"].to_numpy()
    kind = candidate["kind"]
    if kind == "signed":
        selected = (bins == 1) | (bins == 5)
        sign = np.sign(feature)
        spread_effect, pip_effect = sign * future_spread, sign * future_pips
        group = np.zeros(len(frame), dtype=int)
    elif kind == "high_signed":
        selected = bins == 5
        sign = np.sign(frame[candidate["direction"]].to_numpy())
        spread_effect, pip_effect = sign * future_spread, sign * future_pips
        group = np.zeros(len(frame), dtype=int)
    else:
        selected = (bins == 1) | (bins == 5)
        group = np.where(bins == 5, 1, -1)
        if kind == "contrast_abs":
            spread_effect, pip_effect = np.abs(future_spread), np.abs(future_pips)
        else:
            spread_effect = frame[f"future_spread_normalization_{h}s"].to_numpy()
            pip_effect = spread_effect
    valid = selected & np.isfinite(spread_effect) & np.isfinite(pip_effect)
    work = pd.DataFrame({
        "day": frame.loc[valid, "day"].to_numpy(),
        "spread": spread_effect[valid],
        "pips": pip_effect[valid],
        "group": group[valid],
    })
    if kind.startswith("contrast"):
        high = work.loc[work.group == 1].groupby("day")[["spread", "pips"]].mean()
        low = work.loc[work.group == -1].groupby("day")[["spread", "pips"]].mean()
        joined = high.join(low, how="inner", lsuffix="_high", rsuffix="_low")
        return pd.DataFrame({
            "day": joined.index,
            "spread": joined["spread_high"] - joined["spread_low"],
            "pips": joined["pips_high"] - joined["pips_low"],
        }).reset_index(drop=True)
    return work.groupby("day")[["spread", "pips"]].mean().reset_index()


def evaluate(anchor_root: Path, thresholds: dict, selected_ids: set[str] | None = None) -> tuple[dict, dict]:
    registry = [c for c in candidates() if selected_ids is None or c["id"] in selected_ids]
    daily: dict[str, list[pd.DataFrame]] = defaultdict(list)
    pair_year: dict[str, dict] = defaultdict(dict)
    files = sorted(anchor_root.rglob("*.parquet"))
    for path in files:
        pair, year = path.parts[-3], int(path.parts[-2])
        frame = pd.read_parquet(path)
        for candidate in registry:
            rows = effect_rows(frame, candidate, thresholds[pair][candidate["feature"]])
            if rows.empty:
                continue
            rows["pair"] = pair
            rows["year"] = year
            daily[candidate["id"]].append(rows)
    results = {}
    for candidate in registry:
        cid = candidate["id"]
        if not daily[cid]:
            results[cid] = {
                "family": candidate["family"], "feature": candidate["feature"],
                "lookback_seconds": int(cid.split("_")[-2][:-1]), "horizon_seconds": candidate["h"],
                "kind": candidate["kind"], "direction": 0,
                "effect_spread_units": None, "effect_pips": None,
                "bootstrap": {"mean": None, "median_daily": None, "ci_low": None, "ci_high": None,
                              "fraction_positive": None, "fraction_negative": None, "p_two_sided": 1.0},
                "by_pair": {}, "by_year": {}, "pair_direction_count": 0,
                "year_direction_stable": False, "top5_day_absolute_share": 1.0,
                "daily_blocks": 0, "rejection_reason": "INSUFFICIENT_DAILY_CONTRAST_OBSERVATIONS",
            }
            continue
        frame = pd.concat(daily[cid], ignore_index=True)
        pooled = block_bootstrap(frame["spread"].to_numpy())
        pooled_pips = float(frame["pips"].mean())
        by_pair = {p: float(g.spread.mean()) for p, g in frame.groupby("pair")}
        by_year = {str(y): float(g.spread.mean()) for y, g in frame.groupby("year")}
        direction = 1 if pooled["mean"] > 0 else -1
        top5 = float(frame.spread.abs().nlargest(5).sum() / frame.spread.abs().sum())
        results[cid] = {
            "family": candidate["family"], "feature": candidate["feature"],
            "lookback_seconds": int(cid.split("_")[-2][:-1]), "horizon_seconds": candidate["h"],
            "kind": candidate["kind"], "direction": direction,
            "effect_spread_units": pooled["mean"], "effect_pips": pooled_pips,
            "bootstrap": pooled, "by_pair": by_pair, "by_year": by_year,
            "pair_direction_count": sum(np.sign(v) == direction for v in by_pair.values()),
            "year_direction_stable": all(np.sign(v) == direction for v in by_year.values()),
            "top5_day_absolute_share": top5, "daily_blocks": len(frame),
        }
    return results, {cid: pd.concat(rows, ignore_index=True) for cid, rows in daily.items() if rows}


def freeze_discovery(run: Path) -> Path:
    anchor_root = run / "anchors" / "discovery"
    features = sorted({c["feature"] for c in candidates()})
    thresholds = {}
    for pair in PAIRS:
        values = {feature: [] for feature in features}
        for path in sorted((anchor_root / pair).rglob("*.parquet")):
            frame = pd.read_parquet(path, columns=features)
            for feature in features:
                values[feature].append(frame[feature].to_numpy())
        thresholds[pair] = {feature: quantile_boundaries(np.concatenate(parts)) for feature, parts in values.items()}
    results, _ = evaluate(anchor_root, thresholds)
    by_family = defaultdict(dict)
    for cid, value in results.items():
        by_family[value["family"]][cid] = value["bootstrap"]["p_two_sided"]
    fdr = {}
    for family, values in by_family.items():
        fdr.update(benjamini_hochberg(values))
    survivors, rejected = [], []
    for cid, value in results.items():
        ci = value["bootstrap"]
        gates = {
            "fdr": fdr[cid],
            "year_direction_stable": value["year_direction_stable"],
            "at_least_3_pairs": value["pair_direction_count"] >= 3,
            "ci_excludes_zero": confidence_interval_excludes_zero(ci),
            "not_extreme_day_dominated": value["top5_day_absolute_share"] < 0.5,
        }
        value["gates"] = gates
        (survivors if all(gates.values()) else rejected).append(cid)
    payload = {
        "spec_sha256": SPEC_HASH, "thresholds": thresholds, "results": results,
        "survivors": sorted(survivors), "rejected": sorted(rejected),
        "fdr_q": 0.05, "bootstrap_seed": 22001, "bootstrap_resamples": 10000,
    }
    path = run / "discovery_survivors.json"
    text = json.dumps(payload, indent=2, default=json_default) + "\n"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    (run / "discovery_survivors.sha256").write_text(digest + "\n", encoding="utf-8")
    print(json.dumps({"evaluated": len(results), "survivors": len(survivors), "sha256": digest}))
    return path


def freeze_later_stage(run: Path, stage: str) -> Path:
    if stage not in {"CONFIRMATION", "INTERNAL_HOLDOUT"}:
        raise ValueError(f"unsupported later stage {stage}")
    discovery_path = run / "discovery_survivors.json"
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    prior_path = discovery_path if stage == "CONFIRMATION" else run / "confirmation_survivors.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    selected = set(prior["survivors"])
    results, _ = evaluate(run / "anchors" / stage.lower(), discovery["thresholds"], selected)
    survivors, rejected = [], []
    for cid in sorted(selected):
        value = results[cid]
        frozen_direction = discovery["results"][cid]["direction"]
        pair_matches = sum(np.sign(v) == frozen_direction for v in value["by_pair"].values())
        gates = {"frozen_direction": value["direction"] == frozen_direction,
                 "ci_excludes_zero": confidence_interval_excludes_zero(value["bootstrap"]),
                 "at_least_3_pairs_frozen_direction": pair_matches >= 3}
        value["frozen_discovery_direction"] = frozen_direction
        value["pair_frozen_direction_count"] = pair_matches
        value["gates"] = gates
        (survivors if all(gates.values()) else rejected).append(cid)
    payload = {"spec_sha256": SPEC_HASH,
        "dataset_root": "ae0f5b70f686c1b0fff05c0b71f9efb7c3d5da4983eba0df895989dbf6572a91",
        "stage": stage,
        "discovery_survivor_sha256": hashlib.sha256(discovery_path.read_bytes()).hexdigest(),
        "prior_survivor_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        "results": results, "survivors": survivors, "rejected": rejected,
        "thresholds_reused_unchanged": True, "directions_reused_unchanged": True,
        "bootstrap_seed": 22001, "bootstrap_resamples": 10000}
    stem = "confirmation_survivors" if stage == "CONFIRMATION" else "holdout_survivors"
    path = run / f"{stem}.json"
    content = (json.dumps(payload, indent=2, default=json_default) + "\n").encode("utf-8")
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    (run / f"{stem}.sha256").write_bytes((digest + "\n").encode("ascii"))
    print(json.dumps({"stage": stage, "evaluated": len(results), "survivors": len(survivors), "sha256": digest}))
    return path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="phase22a_20260909T220000Z")
    parser.add_argument("--report-root", type=Path, default=Path("reports/phase22a"))
    parser.add_argument("--stage", choices=("DISCOVERY", "CONFIRMATION", "INTERNAL_HOLDOUT"), default="DISCOVERY")
    args = parser.parse_args()
    run = args.report_root / args.run_id
    freeze_discovery(run) if args.stage == "DISCOVERY" else freeze_later_stage(run, args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())