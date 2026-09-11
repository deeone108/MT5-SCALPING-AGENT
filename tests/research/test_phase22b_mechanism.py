from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pytest

from mt5_scalping_agent.research.phase22b_mechanism import (
    SPEC_SHA256,
    InvalidResearchRun,
    apply_quintiles,
    benjamini_hochberg,
    build_design_matrix,
    canonical_sha256,
    fit_wls_clustered_day,
    freeze_quintiles,
    load_frozen_spec,
    prepare_model_rows,
    build_causal_anchor_inputs,
    exact_model_complete_case,
    enforce_minimum_contrast_cells,
)


ROOT = Path(__file__).parents[2]


def test_frozen_spec_canonical_hash_reproduces() -> None:
    path = ROOT / "research" / "phase22b_spec_v7.json"
    assert canonical_sha256(json.loads(path.read_text(encoding="utf-8"))) == SPEC_SHA256
    assert load_frozen_spec(path)["specification_binding"]["version"] == "v7"



def test_frozen_quintiles_are_deterministic_and_fail_closed() -> None:
    boundaries = freeze_quintiles(np.arange(1.0, 101.0))
    assert boundaries == freeze_quintiles(np.arange(1.0, 101.0))
    assert apply_quintiles([0.0, 50.0, 101.0], boundaries).tolist() == [1, 3, 5]
    with pytest.raises(InvalidResearchRun):
        freeze_quintiles([1.0, 1.0, 1.0])


def synthetic_anchors() -> pd.DataFrame:
    anchor = pd.date_range("2019-01-02T00:00:00Z", periods=10, freq="10s").astype("int64")
    return pd.DataFrame(
        {
            "anchor_utc_ns": anchor,
            "quote_utc_ns": anchor,
            "future_quote_60s_utc_ns": anchor + 60_000_000_000,
            "mid": 1.1000,
            "future_mid_60s": 1.1000 + np.arange(10) * 0.00001,
            "spread_pips": np.linspace(0.5, 2.0, 10),
            "trailing_median_spread_pips": 1.0,
            "recent_micro_volatility_pips": np.arange(1.0, 11.0),
            "recent_quote_count": np.arange(5.0, 15.0),
            "baseline_quote_count": 40.0,
            "impulse_15s_pips": np.linspace(-1.0, 1.0, 10),
            "quote_age_seconds": 0.0,
            "baseline_quote_rate": 1.0,
            "baseline_micro_volatility_pips": 2.0,
        }
    )


def test_prepare_rows_uses_timestamp_horizon_not_row_shift() -> None:
    boundaries = (0.7, 0.9, 1.2, 1.6)
    controls = {name: (2.0, 4.0, 6.0, 8.0) for name in ("vol_q", "activity_q", "impulse_abs_q", "trailing_spread_q")}
    rows = prepare_model_rows(
        synthetic_anchors(), pair="EURUSD", exposure_boundaries=boundaries,
        control_boundaries=controls, fixed_discovery_spread_pips=1.0,
    )
    assert set(rows["exposure"]) == {"WIDE", "TIGHT"}
    assert np.allclose(rows["Y_RAW_ABS_60S_PIPS"], np.abs(rows["future_mid_60s"] - rows["mid"]) / 0.0001)
    bad = synthetic_anchors()
    bad.loc[0, "future_quote_60s_utc_ns"] = bad.loc[0, "anchor_utc_ns"] + 60_000_000_001
    with pytest.raises(InvalidResearchRun, match="horizon"):
        prepare_model_rows(bad, pair="EURUSD", exposure_boundaries=boundaries, control_boundaries=controls, fixed_discovery_spread_pips=1.0)


def test_matrix_order_weights_and_wls_are_deterministic() -> None:
    rng = np.random.default_rng(22002)
    n = 80
    rows = pd.DataFrame(
        {
            "exposure": np.where(np.arange(n) % 2, "WIDE", "TIGHT"),
            "pair": "EURUSD",
            "utc_day": np.where(np.arange(n) < 40, "2019-01-02", "2019-01-03"),
            "Y_RAW_ABS_60S_PIPS": 2.0 - 0.3 * (np.arange(n) % 2) + rng.normal(0, 0.01, n),
        }
    )
    model = {"response": "Y_RAW_ABS_60S_PIPS", "predictors": ["intercept", "exposure__WIDE"], "coefficient_names": ["intercept", "exposure__WIDE"]}
    x, y, weights, names = build_design_matrix(rows, model)
    assert names == ["intercept", "exposure__WIDE"]
    assert np.allclose(pd.Series(weights).groupby(rows["utc_day"]).sum(), 1.0)
    first = fit_wls_clustered_day(x, y, weights, names, rows["utc_day"])
    second = fit_wls_clustered_day(x, y, weights, names, rows["utc_day"])
    assert first.coefficient("exposure__WIDE") == second.coefficient("exposure__WIDE")
    assert first.coefficient("exposure__WIDE") < 0


def test_wls_rank_failure_is_invalid_run() -> None:
    x = np.ones((6, 2))
    with pytest.raises(InvalidResearchRun, match="rank-deficient"):
        fit_wls_clustered_day(x, np.arange(6.0), np.ones(6), ["a", "b"], ["d1"] * 3 + ["d2"] * 3)


def test_bh_is_deterministic_and_rejects_incomplete_family() -> None:
    values = {"H_VOL": 0.001, "H_ACTIVITY": 0.02, "H_PAIR": 0.9}
    first = benjamini_hochberg(values, ["H_VOL", "H_ACTIVITY", "H_PAIR"])
    assert first == benjamini_hochberg(values, ["H_VOL", "H_ACTIVITY", "H_PAIR"])
    assert first["H_VOL"]["rejected"] is True
    assert first["H_PAIR"]["rejected"] is False
    with pytest.raises(InvalidResearchRun, match="membership"):
        benjamini_hochberg(values, ["H_VOL"])


def test_v7_causal_ticks_missingness_and_cell_rule() -> None:
    base=pd.Timestamp("2019-01-02T00:00:00Z").value
    times=base+np.arange(2000,dtype="int64")*100_000_000
    mid=1.1+np.sin(np.arange(2000)/20)*.00001
    ticks=pd.DataFrame({"timestamp_utc_ns":times,"bid":mid-.00005,"ask":mid+.00005,"source_row_ordinal":np.arange(2000)})
    out=build_causal_anchor_inputs(ticks,pair="EURUSD",output_start=pd.Timestamp("2019-01-02T00:01:20Z"),output_end=pd.Timestamp("2019-01-02T00:03:00Z"))
    valid=out[out.causal_failure.isna()]
    assert not valid.empty and (valid.quote_utc_ns<=valid.anchor_utc_ns).all()
    assert (valid.future_quote_60s_utc_ns>valid.anchor_utc_ns).all()
    rows=pd.DataFrame({"exposure":["WIDE"]*20+["TIGHT"]*20,"y":[1.0]*40,"pair":["EURUSD"]*40,"utc_day":["2019-01-02"]*40})
    model={"response":"y","predictors":["intercept","exposure__WIDE"],"coefficient_names":["intercept","exposure__WIDE"]}
    kept,attrition=exact_model_complete_case(rows,model)
    assert len(kept)==40 and sum(attrition.values())==0
    assert enforce_minimum_contrast_cells(kept)["evaluable"] is True
    assert enforce_minimum_contrast_cells(kept.iloc[:-1])["evaluable"] is False

def test_wald_rejects_indefinite_restriction_covariance() -> None:
    from mt5_scalping_agent.research.phase22b_mechanism import WLSResult, wald_test
    result=WLSResult(("a","b"),np.array([1.,1.]),np.array([[1.,2.],[2.,1.]]),2,1.)
    with pytest.raises(InvalidResearchRun,match="Wald restriction covariance"):
        wald_test(result,["a","b"])


def test_unknown_categorical_level_fails_closed() -> None:
    model={"response":"y","predictors":["intercept","weekday__TUE"],"coefficient_names":["intercept","weekday__TUE"],"categorical_variables":{"weekday":["MON","TUE","WED","THU","FRI"]}}
    rows=pd.DataFrame({"y":[1.],"weekday":["SAT"],"pair":["EURUSD"],"utc_day":["2019-01-05"]})
    with pytest.raises(InvalidResearchRun,match="categorical"):
        build_design_matrix(rows,model)

def _brute_causal(ticks, pair, start, end):
    ts=ticks.timestamp_utc_ns.to_numpy(np.int64); mid=(ticks.bid.to_numpy(float)+ticks.ask.to_numpy(float))/2; pip=.01 if pair.endswith("JPY") else .0001
    anchors=np.arange(start.value,end.value,10_000_000_000,dtype=np.int64); rows=[]
    for anchor in anchors:
        current=np.flatnonzero(ts<=anchor); target=anchor+60_000_000_000; future=np.flatnonzero(ts<=target)
        if not len(current) or anchor-ts[current[-1]]>2_000_000_000: rows.append((anchor,"current_quote_freshness",np.nan,np.nan)); continue
        fp=future[-1] if len(future) else -1
        if fp<0 or ts[fp]<=anchor or target-ts[fp]>2_000_000_000: rows.append((anchor,"future_quote_freshness",np.nan,np.nan)); continue
        recent=np.flatnonzero((ts>anchor-15_000_000_000)&(ts<=anchor)); baseline=np.flatnonzero((ts>anchor-75_000_000_000)&(ts<=anchor-15_000_000_000))
        rv=np.abs(np.diff(mid[recent])).sum()/pip; bv=np.abs(np.diff(mid[baseline])).sum()/pip
        rows.append((anchor,None,rv,bv))
    return pd.DataFrame(rows,columns=["anchor_utc_ns","causal_failure","recent_micro_volatility_pips","baseline_micro_volatility_pips"])


def test_indexed_anchor_builder_matches_brute_force_windows_and_failures() -> None:
    base=pd.Timestamp("2019-01-02T00:00:00Z"); times=base.value+np.arange(2400,dtype=np.int64)*100_000_000
    mid=1.1+np.sin(np.arange(len(times))/17)*.00002
    ticks=pd.DataFrame({"timestamp_utc_ns":times,"bid":mid-.00005,"ask":mid+.00005,"source_row_ordinal":np.arange(len(times))})
    start=pd.Timestamp("2019-01-02T00:01:20Z"); end=pd.Timestamp("2019-01-02T00:03:00Z")
    fast=build_causal_anchor_inputs(ticks,pair="EURUSD",output_start=start,output_end=end); brute=_brute_causal(ticks,"EURUSD",start,end)
    assert fast.anchor_utc_ns.tolist()==brute.anchor_utc_ns.tolist()
    # Spread-baseline is a later eligibility layer; compare quote-window failures before it.
    assert fast.causal_failure.fillna("OK").replace("spread_baseline","OK").tolist()==brute.causal_failure.fillna("OK").tolist()
    valid=brute.causal_failure.isna()
    np.testing.assert_allclose(fast.loc[valid,"recent_micro_volatility_pips"],brute.loc[valid,"recent_micro_volatility_pips"],rtol=0,atol=1e-12)
    np.testing.assert_allclose(fast.loc[valid,"baseline_micro_volatility_pips"],brute.loc[valid,"baseline_micro_volatility_pips"],rtol=0,atol=1e-12)


def test_indexed_anchor_builder_practical_performance() -> None:
    base=pd.Timestamp("2019-01-02T00:00:00Z").value; count=100_000; times=base+np.arange(count,dtype=np.int64)*100_000_000; mid=1.1+np.sin(np.arange(count)/19)*.00001
    ticks=pd.DataFrame({"timestamp_utc_ns":times,"bid":mid-.00005,"ask":mid+.00005,"source_row_ordinal":np.arange(count)})
    started=time.perf_counter(); out=build_causal_anchor_inputs(ticks,pair="EURUSD",output_start=pd.Timestamp(base+80_000_000_000,unit="ns",tz="UTC"),output_end=pd.Timestamp(base+9_000_000_000_000,unit="ns",tz="UTC")); elapsed=time.perf_counter()-started
    assert len(out)>800 and elapsed<2.0