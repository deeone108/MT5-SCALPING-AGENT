from __future__ import annotations

import json
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
    deterministic_replay,
    authoritative_result_manifest,
    assert_future_perturbation_invariant,
    _cached_daily_block_bootstrap,
    _interaction_strata,
    _linear_contrast,
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
SPEC = json.loads((ROOT / "research/phase22b_spec_v7.json").read_text(encoding="utf-8"))


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


def test_exact_10000_permutation_and_replay() -> None:
    rows=pd.DataFrame({"pair":["EURUSD"]*4,"utc_day":["2019-01-02"]*4,"utc_hour":[1]*4,"vol_q":["Q1"]*4,"activity_q":["Q1"]*4,"anchor_utc_ns":[1,2,3,4],"source_row_ordinal":[0,1,2,3],"exposure":["WIDE","WIDE","TIGHT","TIGHT"],"y":[1.,2.,3.,4.]})
    stat=lambda x: float(x.loc[x.exposure=="WIDE","y"].mean()-x.loc[x.exposure=="TIGHT","y"].mean())
    result=stratified_permutation_diagnostic(rows,stat,observed=stat(rows))
    assert result["resamples"]==10000 and result["seed"]==22003 and 0<=result["p_value"]<=1
    first,digest=deterministic_replay(lambda:{"x":1,"p":result["p_value"]})
    assert first["x"]==1 and len(digest)==64


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