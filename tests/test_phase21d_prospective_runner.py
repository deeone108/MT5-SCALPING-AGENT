import json
from pathlib import Path
import pandas as pd
from scripts.run_phase21d_prospective import COST_SHA,END,HASHES,HYP_SHA,PAIRS,START,REQUIRED,criteria,validate

def result(check=True):
    checks={k:check for k in ("aggregate_positive","three_pairs_positive","negative_pair_does_not_reverse_aggregate","bootstrap_ci_positive","bootstrap_test_survives","pair_concentration","top10_event_concentration")}
    return {"classification":"PROSPECTIVE_HYPOTHESIS_PASSED" if check else "PROSPECTIVE_HYPOTHESIS_FAILED","checks":checks}

def test_criteria_maps_exact_frozen_c1_to_c8():
    values=criteria(result());assert set(values)=={f"C{i}" for i in range(1,9)};assert all(x["pass"] for x in values.values())
    values=criteria(result(False));assert values["C6"]["pass"];assert not values["C1"]["pass"]

def documents():
    hashes={p:{str(y):h for y,h in zip((2024,2025,2026),hs)} for p,hs in HASHES.items()};event=pd.Timestamp("2024-02-01T00:00Z");outcomes=[{"pair":p,"event_time":event.isoformat(),"entry_time":(event+pd.Timedelta(1,unit="min")).isoformat(),"exit_time":(event+pd.Timedelta(61,unit="min")).isoformat(),"status":"AVAILABLE","stress_cost_pips":1.} for p in PAIRS];checks={f"C{i}":{"pass":True} for i in range(1,9)}
    return {"manifest":{"hypothesis_sha256":HYP_SHA,"cost_model_sha256":COST_SHA,"archive_hashes":hashes,"common_start":START.isoformat(),"common_end":END.isoformat()},"holdout_data_integrity":{},"event_population":{},"event_outcomes":outcomes,"pair_results":{},"year_results":{},"bootstrap":{"replicates":10_000,"seed":21_003},"concentration":{},"success_criteria":checks,"phase21d_summary":{"classification":"PROSPECTIVE_HYPOTHESIS_VALIDATED"}}

def test_content_validator_proves_timestamps_costs_and_classification(tmp_path):
    docs=documents();costs={p:{"stress":{"round_trip_cost_pips":1.}} for p in PAIRS}
    for name in REQUIRED:(tmp_path/f"{name}.json").write_text(json.dumps(docs[name]))
    assert validate(tmp_path,costs)["valid"]
    docs["event_outcomes"][0]["entry_time"]=(pd.Timestamp(docs["event_outcomes"][0]["entry_time"])+pd.Timedelta(1,unit="min")).isoformat();(tmp_path/"event_outcomes.json").write_text(json.dumps(docs["event_outcomes"]));assert "timestamp_semantics" in validate(tmp_path,costs)["invalid_components"]
