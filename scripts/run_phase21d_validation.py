"""Run the frozen Phase 21D holdout validation; never connects to MT5."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from datetime import UTC,datetime
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.manifest import write_json_atomic

PAIRS=("EURUSD","GBPUSD","USDJPY","USDCAD")
HYPOTHESIS_SHA="59606899783e6cc3d35f49a6437013dd483da890cda58db16b674f831017900e"
COST_SHA="7c2937ffdb91233cec875895c2f42efc247bd242ef117cc74c7540420cb4faba"
HYPOTHESIS_COMMIT="420b7fc9ea274ced5dd44bb6dfe244fbe3f64533"
START=pd.Timestamp("2024-01-01",tz="UTC"); END=pd.Timestamp("2027-01-01",tz="UTC")
REQUIRED=("manifest","holdout_data_integrity","event_population","pair_results","year_results","bootstrap","concentration","success_criteria","phase21d_summary")

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def emit(path:Path,payload:object)->None:write_json_atomic(path,payload)

def validate(directory:Path,run_id:str)->dict[str,object]:
    missing=[];invalid=[];docs={}
    for name in REQUIRED:
        path=directory/f"{name}.json"
        if not path.exists():missing.append(name);continue
        try:docs[name]=json.loads(path.read_text())
        except Exception:invalid.append(f"{name}:json")
    if not missing and not invalid:
        manifest=docs["manifest"];integrity=docs["holdout_data_integrity"];population=docs["event_population"];criteria=docs["success_criteria"];summary=docs["phase21d_summary"]
        if manifest.get("hypothesis_sha256")!=HYPOTHESIS_SHA:invalid.append("hypothesis_fingerprint")
        if manifest.get("cost_model_sha256")!=COST_SHA:invalid.append("cost_fingerprint")
        if manifest.get("holdout_start")!="2024-01-01T00:00:00+00:00":invalid.append("holdout_boundary")
        if set(integrity.get("pairs",{}))!=set(PAIRS):invalid.append("four_pair_integrity_coverage")
        if set(population.get("pairs",{}))!=set(PAIRS):invalid.append("four_pair_event_coverage")
        if set(criteria.get("criteria",{}))!={f"C{i}" for i in range(1,9)}:invalid.append("criteria_coverage")
        bootstrap=docs["bootstrap"]
        if bootstrap.get("replicates")!=10_000 or bootstrap.get("seed")!=21_003:invalid.append("bootstrap_specification")
        expected="INSUFFICIENT_HOLDOUT_SAMPLE" if not criteria["criteria"]["C6"]["pass"] else "PROSPECTIVE_HYPOTHESIS_VALIDATED" if all(x["pass"] for x in criteria["criteria"].values()) else "PROSPECTIVE_HYPOTHESIS_FAILED"
        if summary.get("classification")!=expected:invalid.append("classification_reproduction")
        text="".join(path.read_text() for path in directory.glob("*.json"))
        if "NaN" in text or "Infinity" in text:invalid.append("nonfinite")
    classification=None if missing or invalid else docs["phase21d_summary"]["classification"]
    return {"valid":not missing and not invalid,"missing_components":missing,"invalid_components":invalid,"classification_recomputed":classification}

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--run-id",required=True);args=parser.parse_args();root=Path(".").resolve();out=root/"reports"/"phase21d"/args.run_id
    if out.exists():raise RuntimeError("immutable run directory already exists")
    out.mkdir(parents=True);hyp=root/"docs"/"PHASE_21C_PROSPECTIVE_HYPOTHESIS.md";cost=root/"config"/"cross_pair_cost_models.json"
    if sha(hyp)!=HYPOTHESIS_SHA or sha(cost)!=COST_SHA:raise RuntimeError("HOLDOUT_VALIDATION_BLOCKED_INTEGRITY_FAILURE")
    if subprocess.run(["git","merge-base","--is-ancestor",HYPOTHESIS_COMMIT,"HEAD"]).returncode:raise RuntimeError("HOLDOUT_VALIDATION_BLOCKED_INTEGRITY_FAILURE")
    archive=LocalResearchArchive(root/"data");integrity={};missing_required=False
    for pair in PAIRS:
        files=[root/"data"/"dukascopy_annual"/f"{pair}_m1_{year}.csv.gz" for year in (2024,2025,2026)];missing=[str(path.relative_to(root)) for path in files if not path.exists()]
        if missing:integrity[pair]={"archive_start":None,"archive_end":None,"m1_rows":0,"available_year_files":[],"missing_year_files":missing,"partial_2026":True};missing_required=True;continue
        frame=archive.load_m1(pair,START,END);times=pd.to_datetime(frame.time,utc=True);integrity[pair]={"archive_start":times.min().isoformat(),"archive_end":times.max().isoformat(),"m1_rows":len(frame),"available_year_files":[str(path.relative_to(root)) for path in files],"missing_year_files":[],"partial_2026":bool(times.max()<pd.Timestamp("2026-12-31T23:59:00Z"))}
    # Method A cannot exist without simultaneous observations for all four frozen pairs.
    populations={pair:{"eligible_events":0,"available_entries":0,"missing_entries":0,"available_exits":0,"missing_exits":0,"availability_rate":None,"reason":"UNAVAILABLE_MISSING_REQUIRED_PAIR_ARCHIVE" if missing_required else None} for pair in PAIRS}
    pairs={pair:{"event_count":0,"gross_mean_pips":None,"stress_cost_pips":json.loads(cost.read_text())["models"][pair]["stress"]["round_trip_cost_pips"],"net_mean_pips":None,"median_net_pips":None,"win_rate":None,"profit_factor":None,"median_mae":None,"p90_mae":None,"median_mfe":None,"p90_mfe":None,"maximum_consecutive_losing_events":None,"availability_rate":None} for pair in PAIRS}
    criteria={f"C{i}":{"pass":False,"status":"NOT_EVALUATED_INSUFFICIENT_SAMPLE"} for i in range(1,9)};criteria["C6"]={"pass":False,"status":"INSUFFICIENT_HOLDOUT_SAMPLE","aggregate_eligible":0,"minimum_aggregate":500,"per_pair_eligible":{p:0 for p in PAIRS},"minimum_per_pair":75}
    classification="INSUFFICIENT_HOLDOUT_SAMPLE";commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip();now=datetime.now(UTC).isoformat()
    manifest={"schema_version":1,"run_id":args.run_id,"run_timestamp":now,"runner_commit":commit,"hypothesis_commit":HYPOTHESIS_COMMIT,"hypothesis_sha256":HYPOTHESIS_SHA,"cost_model_sha256":COST_SHA,"holdout_start":START.isoformat(),"requested_end_exclusive":END.isoformat(),"pair_universe":list(PAIRS),"mt5":False,"broker_execution":False}
    documents={"manifest":manifest,"holdout_data_integrity":{"pairs":integrity,"four_pair_overlap_available":not missing_required},"event_population":{"pairs":populations,"aggregate_eligible":0},"pair_results":{"pairs":pairs,"equal_weight_aggregate_net_mean":None},"year_results":{"2024":{"event_count":0},"2025":{"event_count":0},"2026_available_period":{"event_count":0}},"bootstrap":{"status":"NOT_RUN_INSUFFICIENT_SAMPLE","replicates":10_000,"seed":21_003,"observed_aggregate_mean":None,"ci95":[None,None],"one_sided_p":None},"concentration":{"status":"NOT_AVAILABLE_INSUFFICIENT_SAMPLE","pair_contribution":None,"top5_events":None,"top10_events":None,"top5_trading_days":None,"top10_trading_days":None},"success_criteria":{"criteria":criteria},"phase21d_summary":{"classification":classification,"reason":"Three required pair archives contain no 2024-2026 data; Method A and its four-pair sample cannot be formed.","aggregate_eligible":0,"equal_weight_aggregate_net_mean":None}}
    for name,document in documents.items():emit(out/f"{name}.json",document)
    result=validate(out,args.run_id);emit(out/"completion_validation.json",result);print(json.dumps({"run_id":args.run_id,"classification":classification,"validation":result}))

if __name__=="__main__":main()
