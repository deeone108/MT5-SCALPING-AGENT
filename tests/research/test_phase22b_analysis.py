from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import mt5_scalping_agent.research.phase22b_analysis as analysis_module

from mt5_scalping_agent.research.phase22b_analysis import (
    canonical_artifact_hash,
    classify_phase22b,
    non_actionable_evidence,
    stratified_permutation_diagnostic,
    cluster_robust_score_diagnostic,
    certified_predicate,
    bootstrap_draw_schedule,
    deterministic_replay,
    authoritative_result_manifest,
    development_gate_truths,
    assert_future_perturbation_invariant,
    _cached_daily_block_bootstrap,
    _interaction_strata,
    _linear_contrast,
    DayBlock,
    benchmark_compressed_bootstrap,
    build_day_blocks,
    certified_attenuation_interval,
    certified_quantile,
    compressed_model_bootstrap,
    compressed_pair_day_bootstrap,
    certified_ratio_distribution,
    matrix_only_preflight,
    pair_day_contrast,
    frozen_workload_inventory,
)
from mt5_scalping_agent.research.phase22b_mechanism import (
    InvalidResearchRun,
    WLSResult,
    build_design_matrix,
    daily_block_bootstrap,
    model_contract,
    wald_test,
    fit_wls_clustered_day,
    exact_model_complete_case,
    enforce_minimum_contrast_cells,
)


ROOT = Path(__file__).parents[2]
SPEC = json.loads((ROOT / "research/phase22b_spec_v12.json").read_text(encoding="utf-8"))


def test_all_frozen_models_and_interactions_resolve_exact_order() -> None:
    for model_id in ("M0", "M1", "M2", "M3", "M4", "S_SESSION"):
        contract = model_contract(SPEC, model_id)
        assert contract["predictors"] == contract["coefficient_names"]
    for item in SPEC["interaction_tests"]:
        contract = model_contract(SPEC, item["hypothesis_id"])
        assert contract["coefficient_names"] == item["coefficient_names"]
        assert contract["restriction_order"] == item["restriction_order"]


def test_interaction_columns_are_exact_binary_products() -> None:
    rows = pd.DataFrame(
        {
            "exposure": ["WIDE", "TIGHT", "WIDE"], "pair": ["EURUSD"] * 3,
            "utc_day": ["2019-01-02"] * 3, "vol_q": ["Q2", "Q2", "Q1"],
            "Y_RAW_ABS_60S_PIPS": [1.0, 2.0, 3.0],
        }
    )
    model = {
        "response": "Y_RAW_ABS_60S_PIPS",
        "predictors": ["intercept", "exposure__WIDE", "vol_q__Q2", "WIDE__vol_q__Q2"],
        "coefficient_names": ["intercept", "exposure__WIDE", "vol_q__Q2", "WIDE__vol_q__Q2"],
    }
    matrix, _, _, names = build_design_matrix(rows, model)
    assert names[-1] == "WIDE__vol_q__Q2"
    assert matrix[:, -1].tolist() == [1.0, 0.0, 0.0]


def test_wald_fails_closed_when_frozen_scipy_runtime_is_unavailable(monkeypatch) -> None:
    result = WLSResult(("x",), np.array([1.0]), np.array([[1.0]]), 1, 1.0)
    monkeypatch.setitem(__import__("sys").modules, "scipy", None)
    monkeypatch.delitem(__import__("sys").modules, "scipy.stats", raising=False)
    with pytest.raises(InvalidResearchRun, match="scipy"):
        wald_test(result, ["x"])


def test_year_stratified_bootstrap_is_deterministic_and_copies_whole_days() -> None:
    rows = pd.DataFrame(
        {
            "year": [2019, 2019, 2020, 2020], "utc_day": ["a", "b", "c", "d"],
            "anchor_utc_ns": [1, 2, 3, 4], "pair": ["EURUSD"] * 4, "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    statistic = lambda frame: float(frame["value"].mean())
    first = daily_block_bootstrap(rows, statistic, resamples=20)
    second = daily_block_bootstrap(rows.sample(frac=1, random_state=2), statistic, resamples=20)
    assert first.tolist() == second.tolist()
    assert len(first) == 20


def complete_gates(**updates) -> dict[str, bool]:
    values = {
        "raw_all_gates": False, "no_full_confounder": False, "normalization_replication": False,
        "raw_denominator_failure": False, "amplification_both": False, "m2_material_both": False,
        "vol_activity_fdr_both": False, "session_or_liquidity_material_both": False,
        "session_or_liquidity_fdr_both": False, "pair_specific_both": False,
        "two_partial_or_interaction_blocks": False, "raw_effect_remains": False,
    }
    values.update(updates)
    return values


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"raw_all_gates": True, "no_full_confounder": True}, "GENUINE_SPREAD_STATE_PHENOMENON"),
        ({"normalization_replication": True, "raw_denominator_failure": True, "amplification_both": True}, "NORMALIZATION_ARTIFACT"),
        ({"m2_material_both": True, "vol_activity_fdr_both": True}, "VOLATILITY_OR_ACTIVITY_CONFOUNDING"),
        ({"session_or_liquidity_material_both": True, "session_or_liquidity_fdr_both": True}, "SESSION_OR_LIQUIDITY_PROXY"),
        ({"pair_specific_both": True}, "PAIR_SPECIFIC_EFFECT"),
        ({"two_partial_or_interaction_blocks": True, "raw_effect_remains": True}, "MIXED_MECHANISM"),
        ({}, "PHENOMENON_NOT_CONFIRMED"),
    ],
)
def test_terminal_classification_precedence(updates, expected) -> None:
    assert classify_phase22b(complete_gates(**updates)) == expected
    assert classify_phase22b(complete_gates(**updates), operational_errors=["leakage"]) == "PHASE_22B_INVALID_RESEARCH_RUN"


def test_non_actionable_evidence_is_hard_coded_and_hashable() -> None:
    evidence = non_actionable_evidence(
        run_id="synthetic", code_version="a" * 40, authorization_id="test",
        stage={}, provenance_hashes={"dataset_root": "b" * 64},
    )
    assert evidence["actionable"] is False
    assert evidence["strategy_eligible"] is False
    assert evidence["trade_direction"] is None
    assert len(canonical_artifact_hash(evidence)) == 64


def test_classification_missing_gate_fails_closed() -> None:
    gates = complete_gates()
    gates.pop("raw_all_gates")
    with pytest.raises(InvalidResearchRun, match="missing"):
        classify_phase22b(gates)


def test_v9_score_replaces_permutation_and_is_non_gating() -> None:
    rows=pd.DataFrame({"pair":["EURUSD"]*6,"utc_day":["a","a","b","b","c","c"],"anchor_utc_ns":range(6),"source_row_ordinal":range(6),"exposure":["TIGHT","WIDE"]*3,"Y_RAW_ABS_60S_PIPS":[1.,3.,2.,5.,4.,8.]})
    contract={"response":"Y_RAW_ABS_60S_PIPS","predictors":["intercept","exposure__WIDE"],"coefficient_names":["intercept","exposure__WIDE"]}
    result=cluster_robust_score_diagnostic(rows,contract)
    assert result["role"].endswith("NON_GATING") and result["df"]==1 and 0<=result["p_value"]<=1
    with pytest.raises(InvalidResearchRun,match="superseded"):
        stratified_permutation_diagnostic(rows,None,observed=0)


@pytest.mark.parametrize(("interval","boundary","operator","expected"),[((-1.,-.1),0.,"<=",True),((.1,1.),0.,">=",True),((.1,1.),0.,"<",False),((-1.,-.1),0.,">",False)])
def test_v12_inclusive_endpoint_predicates(interval,boundary,operator,expected):
    assert certified_predicate(interval,boundary,operator) is expected


def test_v12_straddling_interval_fails_closed_and_schedule_replays():
    with pytest.raises(InvalidResearchRun,match="straddles"):
        certified_predicate((-1.,1.),0.,"<=")
    assert certified_predicate((0.,0.),0.,">=") is True
    assert certified_predicate((0.,0.),0.,"<") is False
    assert certified_predicate((-1.,0.),0.,"<=") is True
    assert certified_predicate((0.,1.),0.,">=") is True
    first,h1=bootstrap_draw_schedule({2019:["a","b"],2020:["c"]},resamples=20)
    second,h2=bootstrap_draw_schedule({2020:["c"],2019:["a","b"]},resamples=20)
    np.testing.assert_array_equal(first,second);assert h1==h2 and first.sum(axis=1).tolist()==[3]*20

def test_authoritative_result_manifest_has_schema_fields() -> None:
    task={"task_id":"PH22B-RI-002","required_dataset_hash":"b"*64,"required_spec_hash":"c"*64}
    result=authoritative_result_manifest(task=task,base_commit="a"*40,inputs=[],artifacts=[{"path":"x","sha256":"d"*64}],commands=[],tests=[{"command":"pytest","passed":True}],files_changed=["x"],start_time="2026-01-01T00:00:00Z",end_time="2026-01-01T00:00:01Z")
    assert result["status"]=="COMPLETE" and result["result_commit"] is None
    assert result["terminal_result"]=="DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW"

def test_cr1_and_wald_match_independent_fixed_numeric_reference() -> None:
    # Hand-derived OLS beta=(7/3, 3), CR1 covariance=[[35/36,5/8],[5/8,5/12]].
    x = np.array([[1., 0.], [1., 1.], [1., 0.], [1., 1.], [1., 0.], [1., 1.]])
    y = np.array([1., 3., 2., 5., 4., 8.])
    result = fit_wls_clustered_day(x, y, np.ones(6), ("intercept", "exposure__WIDE"), ["a", "a", "b", "b", "c", "c"])
    np.testing.assert_allclose(result.coefficients, [7 / 3, 3.], rtol=0, atol=1e-14)
    np.testing.assert_allclose(result.covariance, [[35 / 36, 5 / 8], [5 / 8, 5 / 12]], rtol=0, atol=1e-13)
    test = wald_test(result, ["exposure__WIDE"])
    assert test["statistic"] == pytest.approx(21.6, abs=1e-12)
    assert test["df"] == 1
    assert test["raw_p"] == pytest.approx(3.358518329328546e-6, rel=1e-8)


def test_exact_complete_case_reason_precedence_and_twenty_cell_boundary() -> None:
    rows = pd.DataFrame({
        "year": [2019] * 42, "pair": ["EURUSD"] * 42,
        "utc_day": ["2019-01-02"] * 21 + ["2019-01-03"] * 21,
        "anchor_utc_ns": np.arange(42), "exposure": ["WIDE"] * 21 + ["TIGHT"] * 21,
        "Y_RAW_ABS_60S_PIPS": np.arange(42, dtype=float), "causal_failure": [None] * 42,
    })
    rows.loc[0, "causal_failure"] = "current_quote_freshness"
    rows.loc[0, "Y_RAW_ABS_60S_PIPS"] = np.nan
    model = {"response": "Y_RAW_ABS_60S_PIPS", "predictors": ["intercept", "exposure__WIDE"],
             "coefficient_names": ["intercept", "exposure__WIDE"]}
    complete, attrition = exact_model_complete_case(rows, model)
    assert attrition["current_quote_freshness"] == 1 and attrition["response"] == 0
    cells = enforce_minimum_contrast_cells(complete)
    assert cells["counts"]["ALL"] == {"TIGHT": 21, "WIDE": 20}
    assert cells["evaluable"] is True


def test_future_only_leakage_perturbation_preserves_causal_columns() -> None:
    protected = {
        "anchor_utc_ns": [1], "quote_utc_ns": [1], "spread_pips": [1.],
        "trailing_median_spread_pips": [1.], "recent_micro_volatility_pips": [1.],
        "recent_quote_count": [2], "baseline_quote_count": [8], "impulse_15s_pips": [0.],
        "quote_age_seconds": [0.], "baseline_quote_rate": [1.],
        "baseline_micro_volatility_pips": [1.], "exposure": ["WIDE"], "vol_q": ["Q1"],
        "activity_q": ["Q1"], "impulse_sign": ["ZERO"], "impulse_abs_q": ["Q1"],
        "trailing_spread_q": ["Q1"], "future_mid_60s": [2.],
    }
    before = pd.DataFrame(protected); after = before.copy(); after["future_mid_60s"] = 999.
    assert assert_future_perturbation_invariant(before, after)
    after["exposure"] = "TIGHT"
    with pytest.raises(InvalidResearchRun, match="future perturbation"):
        assert_future_perturbation_invariant(before, after)

def test_analyse_stage_populates_complete_cases_before_primary_bootstrap(monkeypatch) -> None:
    rows = pd.DataFrame({
        "year": [2019] * 40, "pair": ["EURUSD"] * 40,
        "utc_day": [f"2019-01-{2 + (i // 10):02d}" for i in range(40)],
        "anchor_utc_ns": np.arange(40), "exposure": ["WIDE", "TIGHT"] * 20,
        "source_row_ordinal": np.arange(40),
        "vol_q": ["Q1"] * 40, "causal_failure": [None] * 40,
        "Y_RAW_ABS_60S_PIPS": [1.0, 2.0] * 20,
        "Y_CURRENT_SPREAD_UNITS": [1.0, 2.0] * 20,
        "Y_TRAILING_SPREAD_UNITS": [1.0, 2.0] * 20,
        "Y_FIXED_DISCOVERY_SCALE": [1.0, 2.0] * 20,
    })
    simple = {"response": "Y_RAW_ABS_60S_PIPS", "predictors": ["intercept", "exposure__WIDE"],
              "coefficient_names": ["intercept", "exposure__WIDE"]}
    monkeypatch.setattr(analysis_module, "model_contract", lambda spec, name: dict(simple))
    monkeypatch.setattr(analysis_module, "_cached_daily_block_bootstrap",
                        lambda frame, statistic, resamples, seed: np.full(resamples, statistic(frame)))
    spec = {"interaction_tests": [{"hypothesis_id": "H_VOL", "restriction_order": ["exposure__WIDE"]}],
            "inference": {"multiple_testing": {"families": [{"id": "controls", "members": ["H_VOL"], "q": 0.05}]}}}
    result = analysis_module.analyse_stage(rows, spec, bootstrap_resamples=20)
    assert result["complete_case_attrition"]["M4"]["total"]["response"] == 0
    assert result["contrast_cells"]["M4"]["counts"]["ALL"] == {"TIGHT": 20, "WIDE": 20}
    assert result["primary_bootstrap"]["replicates"] == 20
    assert set(result["m4_outcomes"]) == {"Y_RAW_ABS_60S_PIPS", "Y_CURRENT_SPREAD_UNITS", "Y_TRAILING_SPREAD_UNITS", "Y_FIXED_DISCOVERY_SCALE"}
    assert set(result["denominator_independent_predicates"]) == {"raw_m4", "fixed_m4", "trailing_m4", "current_spread_m0_negative", "amplification_at_least_four"}

def test_cached_bootstrap_preserves_exact_reference_draw_sequence() -> None:
    rows = pd.DataFrame({"year": [2019, 2019, 2020, 2020], "utc_day": ["a", "b", "c", "d"],
                         "anchor_utc_ns": [1, 2, 3, 4], "pair": ["EURUSD"] * 4,
                         "value": [1., 2., 3., 4.]})
    statistic = lambda frame: float(frame["value"].mean())
    expected = daily_block_bootstrap(rows, statistic, resamples=25, seed=22002)
    actual = _cached_daily_block_bootstrap(rows, statistic, resamples=25, seed=22002)
    np.testing.assert_array_equal(actual, expected)


def test_interaction_strata_reports_scientific_insufficiency_without_fitting() -> None:
    rows = pd.DataFrame({"exposure": ["WIDE"] * 19 + ["TIGHT"] * 20,
                         "vol_q": ["Q1"] * 39})
    result = _interaction_strata(rows, {}, "H_VOL", 3)
    assert result["Q1"]["status"] == "INSUFFICIENT"
    assert all(result[level]["status"] == "INSUFFICIENT" for level in ("Q2", "Q3", "Q4", "Q5"))


def test_linear_interaction_contrast_uses_reference_and_named_increment() -> None:
    result = WLSResult(("exposure__WIDE", "WIDE__vol_q__Q2"), np.array([-0.2, 0.15]), np.eye(2), 2, 1.0)
    assert _linear_contrast(result, "H_VOL", "vol_q", "Q1", "Q1") == pytest.approx(-0.2)
    assert _linear_contrast(result, "H_VOL", "vol_q", "Q2", "Q1") == pytest.approx(-0.05)


def _bootstrap_fixture(seed: int = 7) -> tuple[pd.DataFrame, dict[str, object]]:
    rng = np.random.default_rng(seed); records = []
    for year in (2019, 2020):
        for day in range(5):
            for ordinal in range(12):
                wide = ordinal % 2
                records.append({"year": year, "utc_day": f"{year}-01-{day+1:02d}", "anchor_utc_ns": year*10_000+day*100+ordinal,
                                "pair": "EURUSD", "source_row_ordinal": ordinal, "exposure": "WIDE" if wide else "TIGHT",
                                "Y_RAW_ABS_60S_PIPS": 1.0 + .2*wide + rng.normal(0,.05)})
    contract={"response":"Y_RAW_ABS_60S_PIPS","predictors":["intercept","exposure__WIDE"],"coefficient_names":["intercept","exposure__WIDE"]}
    return pd.DataFrame(records),contract


def test_v12_day_blocks_are_order_invariant_and_qr_diagonal_is_nonnegative() -> None:
    rows, contract = _bootstrap_fixture()
    first, names = build_day_blocks(rows, contract); second, _ = build_day_blocks(rows.sample(frac=1, random_state=9), contract)
    assert names == ("intercept", "exposure__WIDE")
    assert [x.input_sha256 for x in first] == [x.input_sha256 for x in second]
    assert all(np.all(np.diag(block.R) >= 0) for block in first)


def test_v12_compressed_bootstrap_matches_expanded_dgelsd_fixture_and_replays() -> None:
    rows, contract = _bootstrap_fixture(); contrast={"wide": [0., 1.]}
    first=compressed_model_bootstrap(rows,contract,resamples=50,contrast_vectors=contrast)
    second=compressed_model_bootstrap(rows.sample(frac=1,random_state=3),contract,resamples=50,contrast_vectors=contrast)
    assert first["provenance"] == second["provenance"]
    np.testing.assert_array_equal(first["coefficients"],second["coefficients"])
    expected=_cached_daily_block_bootstrap(rows,lambda frame:analysis_module._model_effect(frame,contract),resamples=50,seed=22002)
    np.testing.assert_allclose(first["contrasts"]["wide"],expected,rtol=2e-13,atol=2e-13)
    assert first["fallback_count"] == 0 and set(first["paths"]) == {"SPD"}


def test_v12_fallback_uses_svd_bread_and_multiplicity_not_squared_scores() -> None:
    rows, contract = _bootstrap_fixture(); blocks,_=build_day_blocks(rows,contract)
    multiplicity=np.ones(len(blocks),dtype=np.int64)
    beta_spd,cov_spd,*_ = analysis_module._compressed_fit(blocks,multiplicity,"SPD")
    beta_svd,cov_svd,*_ = analysis_module._compressed_fit(blocks,multiplicity,"STACKED_QR_SVD")
    np.testing.assert_allclose(beta_svd,beta_spd,rtol=2e-13,atol=2e-13)
    np.testing.assert_allclose(cov_svd,cov_spd,rtol=2e-12,atol=2e-12)


def test_v12_matrix_preflight_is_response_independent_and_enforces_fallback_cap() -> None:
    rows, contract = _bootstrap_fixture(); blocks,_=build_day_blocks(rows,contract)
    schedule=np.ones((2,len(blocks)),dtype=np.int64)
    before=matrix_only_preflight(blocks,schedule)
    changed=[DayBlock(x.year,x.utc_day,x.A,x.b*999,x.n,x.R,x.d*999,x.input_sha256) for x in blocks]
    after=matrix_only_preflight(changed,schedule)
    assert before == after
    singular=[DayBlock(x.year,x.utc_day,np.zeros_like(x.A),x.b,x.n,np.zeros_like(x.R),x.d,x.input_sha256) for x in blocks]
    with pytest.raises(InvalidResearchRun,match="invalid bootstrap matrix"):
        matrix_only_preflight(singular,schedule,max_fallbacks=0)


def test_v12_certified_intervals_propagate_quantiles_and_attenuation() -> None:
    low,high=certified_quantile(np.array([[1.,1.1],[2.,2.1],[3.,3.1]]),.5)
    assert low < 2 and high > 2.1
    interval=certified_attenuation_interval(-2.,.01,-1.,.01)
    assert interval[0] < .5 < interval[1]
    with pytest.raises(InvalidResearchRun,match="contains zero"):
        certified_attenuation_interval(0.,.1,-1.,.01)


def test_v12_benchmark_helper_executes_synthetic_primary_and_fallback_paths() -> None:
    result=benchmark_compressed_bootstrap(resamples=10,days=12,k=3,fallback_count=1)
    assert result["resamples"]==10 and result["fallback_count"]==1 and result["passes_30_minutes"]
    assert result["passes_4_gib"] and result["passes_12_hours"] and result["peak_additional_rss_bytes"]>=0
    inventory=frozen_workload_inventory(); assert result["population_count"]==len(inventory["compressed_regression"])==24
    assert result["non_regression_population_count"]==len(inventory["non_regression"])==5
    assert result["full_workload_estimated_seconds"]==pytest.approx(result["wall_seconds"]*29)


def test_v12_pair_day_sufficient_statistics_match_expanded_reference() -> None:
    rows,_=_bootstrap_fixture(); rows["Y_FIXED_DISCOVERY_SCALE"]=rows["Y_RAW_ABS_60S_PIPS"]*2
    result=compressed_pair_day_bootstrap(rows,["Y_RAW_ABS_60S_PIPS","Y_FIXED_DISCOVERY_SCALE"],resamples=30)
    expanded=_cached_daily_block_bootstrap(rows,lambda f:pair_day_contrast(f,"Y_RAW_ABS_60S_PIPS"),resamples=30,seed=22002)
    np.testing.assert_allclose(result["centers"]["Y_RAW_ABS_60S_PIPS"],expanded,rtol=0,atol=2e-16)
    ratio,bounds=certified_ratio_distribution(result["centers"]["Y_FIXED_DISCOVERY_SCALE"],result["intervals"]["Y_FIXED_DISCOVERY_SCALE"],result["centers"]["Y_RAW_ABS_60S_PIPS"],result["intervals"]["Y_RAW_ABS_60S_PIPS"])
    np.testing.assert_allclose(ratio,2.0,rtol=0,atol=2e-15); assert np.all(bounds[:,0]<=ratio) and np.all(ratio<=bounds[:,1])


def test_v12_pair_day_weights_each_eligible_pair_day_equally() -> None:
    rows=pd.DataFrame([
        {"year":2019,"utc_day":"a","pair":"EURUSD","exposure":"WIDE","y":10.},
        {"year":2019,"utc_day":"a","pair":"EURUSD","exposure":"TIGHT","y":0.},
        {"year":2019,"utc_day":"a","pair":"GBPUSD","exposure":"WIDE","y":20.},
        {"year":2019,"utc_day":"a","pair":"GBPUSD","exposure":"TIGHT","y":0.},
        {"year":2019,"utc_day":"b","pair":"EURUSD","exposure":"WIDE","y":0.},
        {"year":2019,"utc_day":"b","pair":"EURUSD","exposure":"TIGHT","y":0.},
    ])
    result=compressed_pair_day_bootstrap(rows,["y"],resamples=30)
    expanded=_cached_daily_block_bootstrap(rows.assign(anchor_utc_ns=np.arange(len(rows)),source_row_ordinal=np.arange(len(rows))),lambda frame:pair_day_contrast(frame,"y"),resamples=30,seed=22002)
    np.testing.assert_allclose(result["centers"]["y"],expanded,rtol=0,atol=2e-15)
    assert 10. in result["centers"]["y"]


def test_v12_ratio_and_attenuation_denominator_touch_zero_fail_closed() -> None:
    with pytest.raises(InvalidResearchRun,match="denominator interval contains zero"):
        certified_ratio_distribution(np.array([1.]),np.array([[.9,1.1]]),np.array([.1]),np.array([[0.,.2]]))
    with pytest.raises(InvalidResearchRun,match="denominator interval contains zero"):
        certified_attenuation_interval(.1,.1,-1.,.01)


def test_v12_development_gate_inclusive_exact_equality_passes() -> None:
    stage={"models":{"M0":{"exposure__WIDE":-.1},"M4":{"exposure__WIDE":-.05}},"primary_bootstrap":{"ci_high":-.01}}
    diagnostics={"year":{"2019":-.1,"2020":-.1,"2021":-.1},"negative_pair_count":4,"largest_pair_fraction":.4,"negative_core_session_count":4,"top_five_day_fraction":.4,"largest_month_fraction":.4}
    assert development_gate_truths(stage,diagnostics)["raw_effect_minimum"] is True


@pytest.mark.parametrize(("n","k","scale"),[(5000,20,1.0),(20000,80,1.0),(5000,20,1e-4)])
def test_v12_expanded_compressed_fixture_matrix(n:int,k:int,scale:float) -> None:
    rng=np.random.default_rng(1200+k); x=rng.standard_normal((n,k)); x[:,0]=1.; x[:,-1]*=scale; beta_true=rng.standard_normal(k); y=x@beta_true+rng.standard_normal(n)*.1; weights=np.ones(n); labels=np.asarray([f"d{i%20:02d}" for i in range(n)])
    reference=fit_wls_clustered_day(x,y,weights,tuple(f"x{i}" for i in range(k)),labels)
    blocks=[]
    for day in sorted(set(labels)):
        idx=np.flatnonzero(labels==day); xg=x[idx]; yg=y[idx]; q,r=np.linalg.qr(xg,mode="reduced"); d=q.T@yg
        for j in range(k):
            if r[j,j]<0:r[j]*=-1;d[j]*=-1
        blocks.append(DayBlock(2019,day,xg.T@xg,xg.T@yg,len(idx),r,d,hashlib.sha256(day.encode()).hexdigest()))
    multiplicity=np.ones(len(blocks),dtype=np.int64); path=matrix_only_preflight(blocks,multiplicity[None,:],max_fallbacks=1)["paths"][0]
    actual,cov,*_=analysis_module._compressed_fit(blocks,multiplicity,path)
    np.testing.assert_allclose(actual,reference.coefficients,rtol=2e-8,atol=2e-8); np.testing.assert_allclose(cov,reference.covariance,rtol=2e-7,atol=2e-7)


def test_v12_fixed_10000_draw_distribution_matches_expanded_reference() -> None:
    rows,contract=_bootstrap_fixture(); blocks,_=build_day_blocks(rows,contract); schedule,_,_=analysis_module._schedule_for_blocks(blocks,10_000,22002); arrays=analysis_module._block_arrays(blocks)
    compressed=np.empty(10_000); expanded=np.empty(10_000)
    x,y,w,names=build_design_matrix(rows.sort_values(["year","utc_day","anchor_utc_ns","pair","source_row_ordinal"],kind="stable"),contract); labels=rows.sort_values(["year","utc_day","anchor_utc_ns","pair","source_row_ordinal"],kind="stable").utc_day.astype(str).to_numpy(); ordered_days=[block.utc_day for block in blocks]
    for i,multiplicity in enumerate(schedule):
        beta,*_=analysis_module._compressed_fit(blocks,multiplicity,"SPD",arrays); compressed[i]=beta[names.index("exposure__WIDE")]
        indices=np.concatenate([np.tile(np.flatnonzero(labels==day),int(count)) for day,count in zip(ordered_days,multiplicity,strict=True) if count>0]); root=np.sqrt(w[indices]); reference=np.linalg.lstsq(x[indices]*root[:,None],y[indices]*root,rcond=1e-12)[0]; expanded[i]=reference[names.index("exposure__WIDE")]
    np.testing.assert_allclose(compressed,expanded,rtol=3e-13,atol=3e-13)
    assert int(np.count_nonzero(compressed>=0.))==int(np.count_nonzero(expanded>=0.))
    np.testing.assert_allclose(np.quantile(compressed,[.025,.975],method="linear"),np.quantile(expanded,[.025,.975],method="linear"),rtol=3e-13,atol=3e-13)


def _frozen_cross_product_rows(n:int=2400)->pd.DataFrame:
    rng=np.random.default_rng(2212); pairs=np.array(["EURUSD","GBPUSD","USDJPY","USDCAD"]); quintiles=np.array(["Q1","Q2","Q3","Q4","Q5"]); signs=np.array(["NEG","ZERO","POS"]); sessions=np.array(["ASIAN","LONDON_PRE_OVERLAP","LONDON_NEW_YORK_OVERLAP","NEW_YORK_POST_OVERLAP","OFF_SESSION"]); weekdays=np.array(["MON","TUE","WED","THU","FRI"])
    frame=pd.DataFrame({"year":2019+np.arange(n)%3,"utc_day":[f"d{i%30:02d}" for i in range(n)],"anchor_utc_ns":np.arange(n,dtype=np.int64),"source_row_ordinal":np.arange(n,dtype=np.int64),"pair":rng.choice(pairs,n),"exposure":rng.choice(["TIGHT","WIDE"],n),"utc_hour":rng.integers(0,24,n),"weekday":rng.choice(weekdays,n),"session":rng.choice(sessions,n),"vol_q":rng.choice(quintiles,n),"activity_q":rng.choice(quintiles,n),"impulse_sign":rng.choice(signs,n),"impulse_abs_q":rng.choice(quintiles,n),"trailing_spread_q":rng.choice(quintiles,n),"recent_micro_volatility_pips":rng.uniform(.01,3,n),"quote_activity_ratio":rng.uniform(.1,4,n),"trailing_median_spread_pips":rng.uniform(.1,3,n),"quote_age_seconds":rng.uniform(0,1,n),"baseline_quote_rate":rng.uniform(.1,10,n),"baseline_micro_volatility_pips":rng.uniform(.01,3,n),"causal_failure":[None]*n})
    signal=rng.normal(size=n)-.1*(frame.exposure=="WIDE").to_numpy()
    for j,response in enumerate(("Y_RAW_ABS_60S_PIPS","Y_CURRENT_SPREAD_UNITS","Y_TRAILING_SPREAD_UNITS","Y_FIXED_DISCOVERY_SCALE")): frame[response]=signal+j+rng.normal(0,.01,n)
    return frame


@pytest.mark.parametrize("model_id",["M1","M2","M3","M4","S_SESSION","H_VOL","H_ACTIVITY","H_HOUR","H_SESSION","H_IMPULSE","H_PAIR","H_LIQUIDITY"])
@pytest.mark.parametrize("response",["Y_RAW_ABS_60S_PIPS","Y_CURRENT_SPREAD_UNITS","Y_TRAILING_SPREAD_UNITS","Y_FIXED_DISCOVERY_SCALE"])
def test_v12_explicit_frozen_model_response_cross_product(model_id:str,response:str)->None:
    rows=_frozen_cross_product_rows(); contract={**model_contract(SPEC,model_id),"response":response}; complete,attrition=exact_model_complete_case(rows,contract)
    assert attrition["response"]==0; x,_,_,names=build_design_matrix(complete,contract); assert names==contract["coefficient_names"] and x.shape[1]==len(names)
    compressed=compressed_model_bootstrap(complete,contract,resamples=1); expected=_cached_daily_block_bootstrap(complete,lambda sample:analysis_module._model_effect(sample,contract),resamples=1,seed=22002)
    index=compressed["coefficient_names"].index("exposure__WIDE"); np.testing.assert_allclose(compressed["coefficients"][:,index],expected,rtol=3e-8,atol=3e-8)
    assert certified_predicate(compressed["coefficient_intervals"][0,index],0.,"<") == bool(expected[0]<0)


def test_v12_statistic_specific_missingness_and_attenuation_pair_population()->None:
    rows=_frozen_cross_product_rows(800); rows.loc[0,"Y_RAW_ABS_60S_PIPS"]=np.nan; rows.loc[1,"Y_CURRENT_SPREAD_UNITS"]=np.nan
    raw,_=exact_model_complete_case(rows,{**model_contract(SPEC,"M1"),"response":"Y_RAW_ABS_60S_PIPS"}); normalized,_=exact_model_complete_case(rows,{**model_contract(SPEC,"M1"),"response":"Y_CURRENT_SPREAD_UNITS"})
    assert 0 not in raw.index and 1 in raw.index and 1 not in normalized.index and 0 in normalized.index
    common=raw.index.intersection(exact_model_complete_case(rows,{**model_contract(SPEC,"M2"),"response":"Y_RAW_ABS_60S_PIPS"})[0].index); assert len(common)==len(raw)
