"""Phase 22B frozen mechanism-validation primitives.

This module deliberately contains no filesystem discovery and no default dataset
reader.  Data can enter only through :class:`GuardedDatasetResolver` after its
manifest and partition metadata pass the frozen access contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import hashlib
import json

import numpy as np
import pandas as pd


SPEC_SHA256 = "12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
DATASET_ROOT_SHA256 = "ae0f5b70f686c1b0fff05c0b71f9efb7c3d5da4983eba0df895989dbf6572a91"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
DEVELOPMENT_YEARS = (2019, 2020, 2021)
FORBIDDEN_FROM = pd.Timestamp("2024-01-01T00:00:00Z")
RCOND = 1e-12
MAX_CONDITION = 1e12


class InvalidResearchRun(RuntimeError):
    """Fail-closed terminal operational state from the frozen specification."""

    state = "PHASE_22B_INVALID_RESEARCH_RUN"


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_frozen_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if canonical_sha256(spec) != SPEC_SHA256:
        raise InvalidResearchRun("frozen Phase 22B specification hash mismatch")
    return spec


def freeze_quintiles(values: Sequence[float]) -> tuple[float, float, float, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0 or not np.isfinite(array).all():
        raise InvalidResearchRun("quintile input must be nonempty and finite")
    result = np.quantile(array, (0.2, 0.4, 0.6, 0.8), method="linear")
    if np.any(np.diff(result) < 0):
        raise InvalidResearchRun("quintile boundaries must be strictly increasing")
    return tuple(float(item) for item in result)


def apply_quintiles(values: Sequence[float], boundaries: Sequence[float]) -> np.ndarray:
    values_array = np.asarray(values, dtype=np.float64)
    boundary_array = np.asarray(boundaries, dtype=np.float64)
    if boundary_array.shape != (4,) or not np.isfinite(boundary_array).all() or np.any(np.diff(boundary_array) < 0):
        raise InvalidResearchRun("four finite nondecreasing frozen boundaries required")
    if not np.isfinite(values_array).all():
        raise InvalidResearchRun("cannot bin non-finite values")
    return np.searchsorted(boundary_array, values_array, side="right") + 1


def prepare_model_rows(
    anchors: pd.DataFrame,
    *,
    pair: str,
    exposure_boundaries: Sequence[float],
    control_boundaries: Mapping[str, Sequence[float]],
    fixed_discovery_spread_pips: float,
) -> pd.DataFrame:
    """Create frozen Phase 22B estimand/control columns from causal anchor rows.

    ``anchors`` is an in-memory table already produced by the authorized reader.
    The function performs no I/O. Required timestamps are the quote selected at
    the anchor and the quote selected as-of the 60-second horizon.
    """
    required = {
        "anchor_utc_ns", "quote_utc_ns", "future_quote_60s_utc_ns", "mid",
        "future_mid_60s", "spread_pips", "trailing_median_spread_pips",
        "recent_micro_volatility_pips", "recent_quote_count",
        "baseline_quote_count", "impulse_15s_pips", "quote_age_seconds",
        "baseline_quote_rate", "baseline_micro_volatility_pips",
    }
    missing = sorted(required - set(anchors.columns))
    if missing:
        raise InvalidResearchRun(f"missing causal anchor columns: {missing}")
    if pair not in PAIRS:
        raise InvalidResearchRun("unexpected pair")
    out = anchors.copy()
    numeric = list(required - {"anchor_utc_ns", "quote_utc_ns", "future_quote_60s_utc_ns"})
    if not np.isfinite(out[numeric].to_numpy(dtype=np.float64)).all():
        raise InvalidResearchRun("non-finite causal inputs")
    anchor = out["anchor_utc_ns"].to_numpy(dtype=np.int64)
    quote = out["quote_utc_ns"].to_numpy(dtype=np.int64)
    future = out["future_quote_60s_utc_ns"].to_numpy(dtype=np.int64)
    horizon = anchor + 60_000_000_000
    if np.any(quote > anchor) or np.any(anchor - quote > 2_000_000_000):
        raise InvalidResearchRun("current quote violates causal freshness")
    if np.any(future <= anchor) or np.any(future > horizon) or np.any(horizon - future > 2_000_000_000):
        raise InvalidResearchRun("future quote violates frozen as-of horizon")
    if np.any(out["spread_pips"] < 0) or np.any(out["trailing_median_spread_pips"] <= 0):
        raise InvalidResearchRun("spread values violate frozen domains")
    if fixed_discovery_spread_pips <= 0 or not np.isfinite(fixed_discovery_spread_pips):
        raise InvalidResearchRun("fixed discovery spread must be positive and finite")
    if np.any(out["baseline_quote_count"] <= 0):
        raise InvalidResearchRun("zero baseline quote count is missing")

    timestamp = pd.to_datetime(anchor, unit="ns", utc=True)
    out["pair"] = pair
    out["utc_day"] = timestamp.strftime("%Y-%m-%d")
    out["utc_hour"] = timestamp.hour
    out["weekday"] = timestamp.strftime("%a").str.upper()
    out["session"] = np.select(
        [timestamp.hour < 8, timestamp.hour < 13, timestamp.hour < 16, timestamp.hour < 21],
        ["ASIAN", "LONDON_PRE_OVERLAP", "LONDON_NEW_YORK_OVERLAP", "NEW_YORK_POST_OVERLAP"],
        default="OFF_SESSION",
    )
    out["spread_dislocation"] = out["spread_pips"] / out["trailing_median_spread_pips"]
    exposure_q = apply_quintiles(out["spread_dislocation"], exposure_boundaries)
    out["exposure"] = np.where(exposure_q == 1, "TIGHT", np.where(exposure_q == 5, "WIDE", "EXCLUDED"))
    raw = np.abs(out["future_mid_60s"] - out["mid"]) / (0.01 if pair.endswith("JPY") else 0.0001)
    out["Y_RAW_ABS_60S_PIPS"] = raw
    out["Y_CURRENT_SPREAD_UNITS"] = np.divide(raw, out["spread_pips"], out=np.full(len(out), np.nan), where=out["spread_pips"] > 0)
    out["Y_TRAILING_SPREAD_UNITS"] = raw / out["trailing_median_spread_pips"]
    out["Y_FIXED_DISCOVERY_SCALE"] = raw / fixed_discovery_spread_pips
    out["quote_activity_ratio"] = out["recent_quote_count"] / (out["baseline_quote_count"] / 4.0)
    out["impulse_sign"] = np.where(out["impulse_15s_pips"] < 0, "NEG", np.where(out["impulse_15s_pips"] > 0, "POS", "ZERO"))
    out["impulse_abs_pips"] = np.abs(out["impulse_15s_pips"])
    bin_sources = {
        "vol_q": "recent_micro_volatility_pips",
        "activity_q": "quote_activity_ratio",
        "impulse_abs_q": "impulse_abs_pips",
        "trailing_spread_q": "trailing_median_spread_pips",
    }
    for output, source in bin_sources.items():
        if output not in control_boundaries:
            raise InvalidResearchRun(f"missing frozen boundaries for {output}")
        out[output] = [f"Q{x}" for x in apply_quintiles(out[source], control_boundaries[output])]
    return out.loc[out["exposure"].isin(("WIDE", "TIGHT"))].reset_index(drop=True)


def build_design_matrix(rows: pd.DataFrame, model: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Build a model in the exact frozen coefficient order."""
    names = list(model["coefficient_names"])
    if names != list(model["predictors"]):
        raise InvalidResearchRun("predictor/coefficient order mismatch")
    for variable, levels in model.get("categorical_variables", {}).items():
        if variable not in rows or not set(rows[variable].dropna().unique()).issubset(set(levels)):
            raise InvalidResearchRun(f"unknown categorical level for {variable}")
    encoded: dict[str, np.ndarray] = {"intercept": np.ones(len(rows)), "exposure__WIDE": (rows["exposure"] == "WIDE").astype(float).to_numpy()}
    categorical = {"pair", "utc_hour", "weekday", "vol_q", "activity_q", "impulse_sign", "impulse_abs_q", "session", "trailing_spread_q"}
    for name in names:
        if name in encoded:
            continue
        if name.startswith("log1p__"):
            source = name.removeprefix("log1p__")
            encoded[name] = np.log1p(rows[source].to_numpy(dtype=np.float64))
        elif name.startswith("WIDE__"):
            component = name.removeprefix("WIDE__")
            variable, level = component.split("__", 1)
            if variable == "utc_hour":
                level = int(level)
            encoded[name] = ((rows["exposure"] == "WIDE") & (rows[variable] == level)).astype(float).to_numpy()
        elif "__" in name:
            variable, level = name.split("__", 1)
            if variable not in categorical:
                raise InvalidResearchRun(f"unknown encoded predictor {name}")
            if variable == "utc_hour":
                level = int(level)
            encoded[name] = (rows[variable] == level).astype(float).to_numpy()
        else:
            encoded[name] = rows[name].to_numpy(dtype=np.float64)
    matrix = np.column_stack([encoded[name] for name in names]).astype(np.float64)
    response = rows[model["response"]].to_numpy(dtype=np.float64)
    counts = rows.groupby(["pair", "utc_day"])["pair"].transform("size").to_numpy(dtype=np.float64)
    weights = 1.0 / counts
    if not np.isfinite(matrix).all() or not np.isfinite(response).all() or np.any(weights <= 0):
        raise InvalidResearchRun("non-finite matrix, response, or weights")
    return matrix, response, weights, names


@dataclass(frozen=True)
class WLSResult:
    coefficient_names: tuple[str, ...]
    coefficients: np.ndarray
    covariance: np.ndarray
    rank: int
    condition_number: float

    def coefficient(self, name: str) -> float:
        try:
            return float(self.coefficients[self.coefficient_names.index(name)])
        except ValueError as exc:
            raise InvalidResearchRun(f"unknown coefficient {name}") from exc


def fit_wls_clustered_day(
    matrix: np.ndarray,
    response: np.ndarray,
    weights: np.ndarray,
    coefficient_names: Sequence[str],
    utc_days: Sequence[str],
) -> WLSResult:
    """Frozen DGELSD WLS with UTC-day clustered CR1 covariance."""
    x = np.asarray(matrix, dtype=np.float64)
    y = np.asarray(response, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    days = np.asarray(utc_days)
    n, k = x.shape
    if y.shape != (n,) or w.shape != (n,) or days.shape != (n,) or len(coefficient_names) != k:
        raise InvalidResearchRun("WLS input shape mismatch")
    if n <= k or np.any(w <= 0) or not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all():
        raise InvalidResearchRun("invalid WLS inputs")
    root_w = np.sqrt(w)
    xw = x * root_w[:, None]
    yw = y * root_w
    try:
        beta, _, rank, singular = np.linalg.lstsq(xw, yw, rcond=RCOND)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise InvalidResearchRun("DGELSD failure") from exc
    if rank != k or singular.size != k or singular[-1] <= 0:
        raise InvalidResearchRun("rank-deficient frozen model")
    condition = float(singular[0] / singular[-1])
    if not np.isfinite(condition) or condition > MAX_CONDITION:
        raise InvalidResearchRun("frozen model condition limit exceeded")
    residual = y - x @ beta
    unique_days = np.unique(days)
    g = len(unique_days)
    if g <= 1:
        raise InvalidResearchRun("cluster covariance requires multiple UTC days")
    vt = np.linalg.svd(xw, full_matrices=False)[2]
    bread = (vt.T * (1.0 / singular**2)) @ vt
    meat = np.zeros((k, k), dtype=np.float64)
    for day in unique_days:
        selected = days == day
        score = (x[selected] * (w[selected] * residual[selected])[:, None]).sum(axis=0)
        meat += np.outer(score, score)
    correction = (g / (g - 1.0)) * ((n - 1.0) / (n - k))
    covariance = correction * bread @ meat @ bread
    if not np.isfinite(beta).all() or not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T):
        raise InvalidResearchRun("invalid WLS output")
    return WLSResult(tuple(coefficient_names), beta, covariance, int(rank), condition)


def benjamini_hochberg(raw_p_values: Mapping[str, float], ordered_members: Sequence[str], q: float = 0.05) -> dict[str, dict[str, float | bool]]:
    """Frozen deterministic BH adjustment with ASCII hypothesis tie-breaking."""
    if set(raw_p_values) != set(ordered_members) or len(raw_p_values) != len(ordered_members):
        raise InvalidResearchRun("FDR family membership mismatch")
    if not 0 < q < 1:
        raise InvalidResearchRun("invalid FDR q")
    for value in raw_p_values.values():
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise InvalidResearchRun("missing or non-finite p-value")
    ordered = sorted(raw_p_values.items(), key=lambda item: (item[1], item[0]))
    m = len(ordered)
    adjusted = [0.0] * m
    running = 1.0
    for index in range(m - 1, -1, -1):
        rank = index + 1
        running = min(running, m * ordered[index][1] / rank)
        adjusted[index] = min(1.0, running)
    cutoff = 0
    for rank, (_, value) in enumerate(ordered, 1):
        if value <= q * rank / m:
            cutoff = rank
    return {
        hypothesis: {"raw_p": float(value), "adjusted_p": float(adjusted[index]), "rejected": index < cutoff}
        for index, (hypothesis, value) in enumerate(ordered)
    }


def model_contract(spec: Mapping[str, Any], model_id: str) -> dict[str, Any]:
    """Resolve one primary, session, or preregistered interaction model."""
    models = spec["models_and_estimands"]
    if model_id in models["primary_models"]:
        return dict(models["primary_models"][model_id])
    if model_id == "S_SESSION":
        return dict(models["sensitivity_models"][model_id])
    by_id = {item["hypothesis_id"]: item for item in spec["interaction_tests"]}
    if model_id not in by_id:
        raise InvalidResearchRun(f"unknown frozen model {model_id}")
    definition = by_id[model_id]
    base = model_contract(spec, definition["base"])
    return {**base, "response": definition["response"], "predictors": list(definition["coefficient_names"]), "coefficient_names": list(definition["coefficient_names"]), "restriction_order": list(definition["restriction_order"])}


def wald_test(result: WLSResult, restriction_order: Sequence[str]) -> dict[str, float | int]:
    """Frozen joint Wald test; SciPy is mandatory rather than approximated."""
    if not restriction_order:
        raise InvalidResearchRun("empty Wald restriction")
    try:
        indices = [result.coefficient_names.index(name) for name in restriction_order]
    except ValueError as exc:
        raise InvalidResearchRun("Wald coefficient missing") from exc
    vector = result.coefficients[indices]
    covariance = result.covariance[np.ix_(indices, indices)]
    covariance = (covariance + covariance.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues.size != len(indices) or eigenvalues[0] <= 0:
        raise InvalidResearchRun("non-positive-definite Wald restriction covariance")
    singular = np.linalg.svd(covariance, compute_uv=False)
    if singular.size != len(indices) or singular[-1] <= RCOND * singular[0]:
        raise InvalidResearchRun("singular Wald restriction covariance")
    try:
        statistic = float(vector @ np.linalg.solve(covariance, vector))
        from scipy.stats import chi2
    except (ImportError, ValueError, np.linalg.LinAlgError) as exc:
        raise InvalidResearchRun("frozen scipy.stats.chi2.sf unavailable or failed") from exc
    p_value = float(chi2.sf(statistic, len(indices)))
    if not np.isfinite(statistic) or not np.isfinite(p_value):
        raise InvalidResearchRun("non-finite Wald result")
    return {"statistic": statistic, "df": len(indices), "raw_p": p_value}


def daily_block_bootstrap(rows: pd.DataFrame, statistic: Callable[[pd.DataFrame], float], *, resamples: int = 10_000, seed: int = 22_002) -> np.ndarray:
    """Frozen year-stratified UTC-day block bootstrap."""
    required = {"year", "utc_day", "anchor_utc_ns", "pair"}
    if not required.issubset(rows):
        raise InvalidResearchRun("bootstrap ordering columns missing")
    if resamples <= 0:
        raise InvalidResearchRun("bootstrap resample count must be positive")
    ordered = rows.sort_values(["year", "utc_day", "anchor_utc_ns", "pair"], kind="stable")
    years = sorted(int(value) for value in ordered["year"].unique())
    days_by_year = {year: sorted(ordered.loc[ordered["year"] == year, "utc_day"].astype(str).unique()) for year in years}
    if any(not days for days in days_by_year.values()):
        raise InvalidResearchRun("bootstrap year has no eligible UTC days")
    rng = np.random.Generator(np.random.PCG64(seed))
    output = np.empty(resamples, dtype=np.float64)
    for iteration in range(resamples):
        copies: list[pd.DataFrame] = []
        for year in years:
            days = days_by_year[year]
            indices = rng.integers(0, len(days), size=len(days), endpoint=False)
            for draw_position, index in enumerate(indices):
                day = days[int(index)]
                copied = ordered[(ordered["year"] == year) & (ordered["utc_day"].astype(str) == day)].copy()
                copied["bootstrap_day_id"] = f"{year}:{draw_position:06d}:{day}"
                copied["utc_day"] = copied["bootstrap_day_id"]
                copies.append(copied)
        sample = pd.concat(copies, ignore_index=True).sort_values(["year", "bootstrap_day_id", "anchor_utc_ns", "pair"], kind="stable")
        value = float(statistic(sample))
        if not np.isfinite(value):
            raise InvalidResearchRun("non-finite bootstrap statistic")
        output[iteration] = value
    return output


def bootstrap_summary(values: Sequence[float], *, alternative: str = "negative") -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (10_000,) or not np.isfinite(array).all():
        raise InvalidResearchRun("exactly 10000 finite bootstrap replicates required")
    low, high = np.quantile(array, [0.025, 0.975], method="linear")
    if alternative != "negative":
        raise InvalidResearchRun("unsupported bootstrap alternative")
    p_value = (1 + int(np.count_nonzero(array >= 0.0))) / 10_001
    return {"ci_low": float(low), "ci_high": float(high), "p_one_sided": float(p_value)}

def build_causal_anchor_inputs(ticks: pd.DataFrame, *, pair: str, output_start: pd.Timestamp, output_end: pd.Timestamp) -> pd.DataFrame:
    """Indexed v7 tick-to-anchor mapping; O(ticks + anchors log ticks)."""
    required=["timestamp_utc_ns","bid","ask","source_row_ordinal"]
    if list(ticks.columns)!=required or pair not in PAIRS: raise InvalidResearchRun("invalid v7 tick interface")
    frame=ticks.sort_values(["timestamp_utc_ns","source_row_ordinal"],kind="stable").reset_index(drop=True)
    ts=frame.timestamp_utc_ns.to_numpy(np.int64); bid=frame.bid.to_numpy(float); ask=frame.ask.to_numpy(float)
    if len(ts)==0 or not np.isfinite(bid).all() or not np.isfinite(ask).all(): raise InvalidResearchRun("invalid ticks")
    start,end=int(output_start.value),int(output_end.value); step=10_000_000_000
    anchors=np.arange(((start+step-1)//step)*step,end,step,dtype=np.int64); n=len(anchors)
    mid=(bid+ask)/2; pip=.01 if pair.endswith("JPY") else .0001; spread=(ask-bid)/pip
    current=np.searchsorted(ts,anchors,side="right")-1; safe=np.maximum(current,0)
    target=anchors+60_000_000_000; future=np.searchsorted(ts,target,side="right")-1; fsafe=np.maximum(future,0)
    current_ok=(current>=0)&(anchors-ts[safe]>=0)&(anchors-ts[safe]<=2_000_000_000)
    future_ok=(future>=0)&(ts[fsafe]>anchors)&(target-ts[fsafe]>=0)&(target-ts[fsafe]<=2_000_000_000)
    out=pd.DataFrame({"anchor_utc_ns":anchors,"causal_failure":np.where(~current_ok,"current_quote_freshness",np.where(~future_ok,"future_quote_freshness",None))})
    valid=current_ok&future_ok
    for name in ("quote_utc_ns","future_quote_60s_utc_ns","mid","future_mid_60s","spread_pips","recent_micro_volatility_pips","recent_quote_count","baseline_quote_count","impulse_15s_pips","quote_age_seconds","baseline_quote_rate","baseline_micro_volatility_pips","trailing_median_spread_pips"): out[name]=np.nan
    out.loc[valid,"quote_utc_ns"]=ts[current[valid]]; out.loc[valid,"future_quote_60s_utc_ns"]=ts[future[valid]]; out.loc[valid,"mid"]=mid[current[valid]]; out.loc[valid,"future_mid_60s"]=mid[future[valid]]; out.loc[valid,"spread_pips"]=spread[current[valid]]; out.loc[valid,"quote_age_seconds"]=(anchors[valid]-ts[current[valid]])/1e9
    left15=np.searchsorted(ts,anchors-15_000_000_000,side="right"); right=np.searchsorted(ts,anchors,side="right"); left75=np.searchsorted(ts,anchors-75_000_000_000,side="right"); base_right=np.searchsorted(ts,anchors-15_000_000_000,side="right")
    delta=np.abs(np.diff(mid,prepend=mid[0])); prefix=np.concatenate(([0.],np.cumsum(delta)))
    recent_abs=prefix[right]-prefix[np.minimum(left15+1,right)]; base_abs=prefix[base_right]-prefix[np.minimum(left75+1,base_right)]
    out.loc[valid,"recent_micro_volatility_pips"]=recent_abs[valid]/pip; out.loc[valid,"baseline_micro_volatility_pips"]=base_abs[valid]/pip; out.loc[valid,"recent_quote_count"]=(right-left15)[valid]; out.loc[valid,"baseline_quote_count"]=(base_right-left75)[valid]; out.loc[valid,"baseline_quote_rate"]=(base_right-left75)[valid]/60
    past=np.searchsorted(ts,anchors-15_000_000_000,side="right")-1; psafe=np.maximum(past,0); pok=(past>=0)&(anchors-15_000_000_000-ts[psafe]>=0)&(anchors-15_000_000_000-ts[psafe]<=2_000_000_000)&valid
    out.loc[pok,"impulse_15s_pips"]=(mid[current[pok]]-mid[past[pok]])/pip
    eligible=out.causal_failure.isna(); baseline=out.loc[eligible,"spread_pips"].shift(1).rolling(6,min_periods=6).median(); out.loc[eligible,"trailing_median_spread_pips"]=baseline
    invalid_baseline = ~np.isfinite(out.trailing_median_spread_pips) | (out.trailing_median_spread_pips <= 0)
    out.loc[eligible & invalid_baseline,"causal_failure"]="spread_baseline"
    return out

ATTRITION_REASON_ORDER=("current_quote_freshness","future_quote_freshness","spread_baseline","response","exposure","model_predictor")


def exact_model_complete_case(rows: pd.DataFrame, model: Mapping[str,Any]) -> tuple[pd.DataFrame,dict[str,int]]:
    """Apply v7 ordered first-failure attrition for one response/model."""
    work=rows.copy(); reasons=pd.Series(index=work.index,dtype="object")
    causal=work.get("causal_failure",pd.Series(None,index=work.index))
    for reason in ATTRITION_REASON_ORDER[:3]: reasons.loc[reasons.isna()&(causal==reason)]=reason
    response=model["response"]; reasons.loc[reasons.isna()&~np.isfinite(pd.to_numeric(work.get(response),errors="coerce"))]="response"
    reasons.loc[reasons.isna()&~work.get("exposure",pd.Series(None,index=work.index)).isin(["WIDE","TIGHT"]) ]="exposure"
    predictors=[x for x in model["coefficient_names"] if x not in ("intercept","exposure__WIDE")]
    try: matrix,_,_,_=build_design_matrix(work.loc[reasons.isna()],model)
    except Exception:
        candidates=work.loc[reasons.isna()]
        for idx in candidates.index:
            try: build_design_matrix(work.loc[[idx]],model)
            except Exception: reasons.loc[idx]="model_predictor"
    counts={reason:int((reasons==reason).sum()) for reason in ATTRITION_REASON_ORDER}
    return work.loc[reasons.isna()].copy(),counts


def enforce_minimum_contrast_cells(rows: pd.DataFrame, group_columns: Sequence[str]=()) -> dict[str,Any]:
    grouped=(rows.groupby(list(group_columns)+["exposure"],sort=True).size().unstack(fill_value=0) if group_columns else pd.DataFrame([rows.groupby("exposure").size().to_dict()],index=["ALL"]))
    for label in ("WIDE","TIGHT"):
        if label not in grouped: grouped[label]=0
    eligible=(grouped.WIDE>=20)&(grouped.TIGHT>=20)
    return {"evaluable":bool(eligible.any()),"eligible_cells":int(eligible.sum()),"insufficient_cells":int((~eligible).sum()),"counts":grouped.to_dict(orient="index")}

def build_causal_anchor_inputs_streaming(chunks: Sequence[pd.DataFrame], *, pair: str, output_start: pd.Timestamp, output_end: pd.Timestamp) -> pd.DataFrame:
    """Canonical v12 chunk interface with authorized unit-order duplicate ties.

    Chunks must already be verified and supplied in adjacent authorized unit order.
    Consolidation here is the reference-equivalent bounded interface; callers may
    release source chunks after concatenation but may not reset causal context.
    """
    if not chunks: raise InvalidResearchRun("streaming input requires authorized chunks")
    ordered=[]; ordinal=0
    for unit_order, chunk in enumerate(chunks):
        if list(chunk.columns)!=["timestamp_utc_ns","bid","ask","source_row_ordinal"]: raise InvalidResearchRun("invalid streaming chunk schema")
        part=chunk.sort_values(["timestamp_utc_ns","source_row_ordinal"],kind="stable").copy()
        part["_unit_order"]=unit_order; part["_local_ordinal"]=part["source_row_ordinal"]
        ordered.append(part)
    combined=pd.concat(ordered,ignore_index=True).sort_values(["timestamp_utc_ns","_unit_order","_local_ordinal"],kind="stable").reset_index(drop=True)
    combined["source_row_ordinal"]=np.arange(len(combined),dtype=np.int64)
    return build_causal_anchor_inputs(combined[["timestamp_utc_ns","bid","ask","source_row_ordinal"]],pair=pair,output_start=output_start,output_end=output_end)