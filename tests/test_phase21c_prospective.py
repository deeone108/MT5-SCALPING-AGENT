import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from mt5_scalping_agent.research.phase21c_prospective import PAIRS,load_canonical_costs,target_reversion_direction
from mt5_scalping_agent.research.phase21c_outcomes import build_event_outcomes
from mt5_scalping_agent.research.phase21c_inference import evaluate_hypothesis

def costs():
    return {p:{"commission_per_lot_per_side_usd":2.,"base":{"round_trip_cost_pips":1.,"spread_points":2.,"slippage_points":1.},"stress":{"round_trip_cost_pips":2.,"spread_points":4.,"slippage_points":2.}} for p in PAIRS}

@pytest.mark.parametrize(("pair","positive","negative"),[("EURUSD",1,-1),("GBPUSD",1,-1),("USDJPY",-1,1),("USDCAD",-1,1)])
def test_direction_algebra_all_pairs(pair,positive,negative):
    assert target_reversion_direction(pair,2)==positive
    assert target_reversion_direction(pair,-2)==negative

def fixture(missing=None):
    t=pd.Timestamp("2020-01-01T00:00Z");event=pd.DataFrame({"pair":["EURUSD"],"event_time":[t],"residual":[2.]});times=pd.date_range(t+pd.Timedelta(1,unit="min"),periods=61,freq="1min");observations=pd.DataFrame({"pair":"EURUSD","time":times,"close":1+np.arange(61)*.0001})
    if missing is not None:observations=observations.drop(index=missing)
    return event,observations

def test_next_observation_entry_exact_exit_and_costs():
    event,observations=fixture();row=build_event_outcomes(event,observations,costs(),start="2020-01-01",end_exclusive="2021-01-01").iloc[0]
    assert row.entry_time==event.event_time.iat[0]+pd.Timedelta(1,unit="min")
    assert row.exit_time==row.entry_time+pd.Timedelta(60,unit="min")
    assert row.gross_directional_pips==pytest.approx(60)
    assert row.net_directional_pips==pytest.approx(58)
    assert row.base_net_directional_pips==pytest.approx(59)
    assert (row.stress_spread_points,row.stress_slippage_points,row.commission_per_lot_per_side_usd)==(4.,2.,2.)

def test_canonical_cost_model_is_the_only_pair_cost_source():
    models=load_canonical_costs(Path("config/cross_pair_cost_models.json"))
    assert models["EURUSD"]["stress"]["round_trip_cost_pips"]==1.2
    assert models["USDJPY"]["base"]["round_trip_cost_pips"]==1.039172

@pytest.mark.parametrize(("missing","status"),[(0,"MISSING_EXACT_ENTRY"),(60,"MISSING_EXACT_EXIT"),(30,"MISSING_EXACT_PATH")])
def test_missing_exact_observation_is_unavailable(missing,status):
    event,observations=fixture(missing)
    assert build_event_outcomes(event,observations,costs(),start="2020-01-01",end_exclusive="2021-01-01").status.iat[0]==status

def test_event_deduplication_is_frozen_at_sixty_minutes():
    event,observations=fixture();event=pd.concat([event,event.assign(event_time=event.event_time+pd.Timedelta(30,unit="min")),event.assign(event_time=event.event_time+pd.Timedelta(60,unit="min"))]);observations=pd.concat([observations,observations.assign(time=observations.time+pd.Timedelta(60,unit="min"))]).drop_duplicates("time")
    assert len(build_event_outcomes(event,observations,costs(),start="2020-01-01",end_exclusive="2021-01-01"))==2

def outcome_frame(n=125,net=1.):
    rows=[]
    for j,pair in enumerate(PAIRS):
        for i in range(n):rows.append({"pair":pair,"event_time":pd.Timestamp("2020-01-01",tz="UTC")+pd.Timedelta(int(i),unit="D")+pd.Timedelta(int(j),unit="min"),"status":"AVAILABLE","net_directional_pips":net,"gross_directional_pips":net+2,"stress_cost_pips":2.,"mfe_pips":3.,"mae_pips":-1.})
    return pd.DataFrame(rows)

def test_insufficient_sample_classification():
    assert evaluate_hypothesis(outcome_frame(74))["classification"]=="INSUFFICIENT_HOLDOUT_SAMPLE"

def test_aggregate_success_and_concentration_checks():
    result=evaluate_hypothesis(outcome_frame());assert result["classification"]=="PROSPECTIVE_HYPOTHESIS_PASSED";assert result["equal_weight_mean_net_pips"]==1;assert result["bootstrap"]["replicates"]==10_000;assert result["checks"]["pair_concentration"];assert result["checks"]["top10_event_concentration"]

def test_failure_classification():
    assert evaluate_hypothesis(outcome_frame(net=-1.))["classification"]=="PROSPECTIVE_HYPOTHESIS_FAILED"

def test_post_2023_requires_explicit_authorization():
    event,observations=fixture()
    with pytest.raises(PermissionError):build_event_outcomes(event,observations,costs(),start="2024-01-01",end_exclusive="2025-01-01")
