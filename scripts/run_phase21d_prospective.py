"""Execute the single frozen Phase 21D prospective holdout validation."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,time
from datetime import UTC,datetime
from pathlib import Path
import numpy as np
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair_edge_discovery import causal_bars,oriented_return
from mt5_scalping_agent.research.relative_value_discovery import standardize_prior,causal_percentile_valid,bucket,entry_events,dedup
from mt5_scalping_agent.research.phase21c_prospective import PAIRS,load_canonical_costs
from mt5_scalping_agent.research.phase21c_outcomes import build_event_outcomes
from mt5_scalping_agent.research.phase21c_inference import evaluate_hypothesis
from mt5_scalping_agent.research.manifest import write_json_atomic

START=pd.Timestamp("2024-01-01T22:04:00Z");END=pd.Timestamp("2026-08-21T20:59:00Z");HYP_SHA="59606899783e6cc3d35f49a6437013dd483da890cda58db16b674f831017900e";COST_SHA="7c2937ffdb91233cec875895c2f42efc247bd242ef117cc74c7540420cb4faba";HYP_COMMIT="420b7fc9ea274ced5dd44bb6dfe244fbe3f64533"
HASHES={"EURUSD":("99c121ed88da5f749e2104ae5623429431465c0b66c4ce866a2e705a00e317b8","7d00cf38c5886ad7a09a2bc8cf0a0407fa29869c99fe9161da9a5f5971957312","3f19f01d56bbce1038fe29a7ca3e88364a6afa9f9a07e7fd6375b7329e6e4b50"),"GBPUSD":("915ce11e256a91eeb30ad193123c617f757d6fa89698372f643664a37d278ced","41347debd4287044721c4adb239f2a8826d568a8102e563827ae0f297f079332","27d74698ff6ed2248cca612f4a3252c353feacb3c1cabc26d36037c036d89a70"),"USDJPY":("b198fd4c2b5b51de7fb178bc07ca2426c21910db9f6dab42df5809bfde390abc","d35062953bc803b91ede01c2e78bac37b2b2e180ce31b2d44c01747522ad18cb","3036aa6a82d397faed07b87e4c9160e0e62fccab608f97fd6e5b7e0242afb69f"),"USDCAD":("0a9125618edbfebc60b3b6e451b3995b7eb2bee3001e6430d0144fe93f1e68e1","9dc02517302806e9a0d2d76c115efdd7475ce6852e649f27d7ef07900433188d","2f83036d248edf6fd0fd0c185d5932edb1f805a5a85fc1fb4bc4db39909f9258")}
REQUIRED=("manifest","holdout_data_integrity","event_population","event_outcomes","pair_results","year_results","bootstrap","concentration","success_criteria","phase21d_summary")

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,(pd.Timestamp,datetime)):return value.isoformat()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value
def records(frame:pd.DataFrame):return clean(frame.to_dict("records"))

def method_a_frames(raw:dict[str,pd.DataFrame])->dict[str,pd.DataFrame]:
    base={}
    for pair,m1 in raw.items():
        m5=causal_bars(m1,5);ret=oriented_return(pair,m5["return"]);base[pair]=pd.DataFrame({"event_time":m5.completed_time,"z":standardize_prior(ret,5760)})
    wide=pd.DataFrame({p:f.set_index("event_time").z for p,f in base.items()});result={}
    for pair,frame in base.items():
        other=wide.drop(columns=pair);common=other.mean(axis=1).where(other.notna().all(axis=1));x=frame.set_index("event_time");x["common"]=common;x["residual"]=x.z-x.common;x["abs_residual"]=x.residual.abs();x["residual_percentile"]=causal_percentile_valid(x.abs_residual,5760);x["bucket"]=bucket(x.residual_percentile);x["pair"]=pair;result[pair]=x.reset_index()
    return result

def concentration(outcomes:pd.DataFrame,result:dict)->dict:
    x=outcomes[outcomes.status.eq("AVAILABLE")].copy();x["absolute_effect"]=x.net_directional_pips.abs();total=float(x.absolute_effect.sum());days=x.groupby(pd.to_datetime(x.event_time,utc=True).dt.date).absolute_effect.sum().sort_values(ascending=False);return {"pair_contribution":result.get("pair_absolute_effect_contribution"),"top5_events":float(x.absolute_effect.nlargest(5).sum()/total),"top10_events":float(x.absolute_effect.nlargest(10).sum()/total),"top5_trading_days":float(days.head(5).sum()/total),"top10_trading_days":float(days.head(10).sum()/total)}

def criteria(result:dict)->dict:
    if result["classification"]=="INSUFFICIENT_HOLDOUT_SAMPLE":return {f"C{i}":{"pass":i==6 and False,"status":"INSUFFICIENT_SAMPLE"} for i in range(1,9)}
    keys=("aggregate_positive","three_pairs_positive","negative_pair_does_not_reverse_aggregate","bootstrap_ci_positive","bootstrap_test_survives",None,"pair_concentration","top10_event_concentration");return {f"C{i+1}":{"pass":True if i==5 else bool(result["checks"][key]),"status":"PASS" if (True if i==5 else result["checks"][key]) else "FAIL"} for i,key in enumerate(keys)}

def validate(directory:Path,costs:dict)->dict:
    invalid=[];docs={}
    for name in REQUIRED:
        try:docs[name]=json.loads((directory/f"{name}.json").read_text())
        except Exception:invalid.append(f"{name}:missing_or_json")
    if not invalid:
        m=docs["manifest"]
        if m["hypothesis_sha256"]!=HYP_SHA:invalid.append("hypothesis_hash")
        if m["cost_model_sha256"]!=COST_SHA:invalid.append("cost_hash")
        if m["archive_hashes"]!=clean({p:{str(y):h for y,h in zip((2024,2025,2026),hs)} for p,hs in HASHES.items()}):invalid.append("archive_hashes")
        if m["common_start"]!=START.isoformat() or m["common_end"]!=END.isoformat():invalid.append("boundary")
        outcomes=docs["event_outcomes"];pairs={x["pair"] for x in outcomes}
        if pairs!=set(PAIRS):invalid.append("pair_coverage")
        for row in outcomes:
            event=pd.Timestamp(row["event_time"]);entry=pd.Timestamp(row["entry_time"]);exit_time=pd.Timestamp(row["exit_time"])
            if event<START or event>END:invalid.append("event_boundary");break
            if entry!=event+pd.Timedelta(1,unit="min") or exit_time!=entry+pd.Timedelta(60,unit="min"):invalid.append("timestamp_semantics");break
            if row["status"]=="AVAILABLE" and row["stress_cost_pips"]!=costs[row["pair"]]["stress"]["round_trip_cost_pips"]:invalid.append("stress_cost");break
        b=docs["bootstrap"]
        if b.get("replicates")!=10_000 or b.get("seed")!=21_003:invalid.append("bootstrap")
        c=docs["success_criteria"]
        if set(c)!={f"C{i}" for i in range(1,9)}:invalid.append("criteria")
        expected="INSUFFICIENT_HOLDOUT_SAMPLE" if not c["C6"]["pass"] else "PROSPECTIVE_HYPOTHESIS_VALIDATED" if all(v["pass"] for v in c.values()) else "PROSPECTIVE_HYPOTHESIS_FAILED"
        if docs["phase21d_summary"]["classification"]!=expected:invalid.append("classification")
        text="".join(p.read_text() for p in directory.glob("*.json"))
        if "NaN" in text or "Infinity" in text:invalid.append("nonfinite")
    return {"valid":not invalid,"invalid_components":invalid,"classification_recomputed":None if invalid else docs["phase21d_summary"]["classification"]}

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--run-id",required=True);args=parser.parse_args();started=time.perf_counter();root=Path(".").resolve();out=root/"reports"/"phase21d"/args.run_id
    if out.exists():raise RuntimeError("immutable run directory already exists")
    if sha(root/"docs"/"PHASE_21C_PROSPECTIVE_HYPOTHESIS.md")!=HYP_SHA or sha(root/"config"/"cross_pair_cost_models.json")!=COST_SHA:raise RuntimeError("HOLDOUT_VALIDATION_BLOCKED_INTEGRITY_FAILURE")
    actual={p:tuple(sha(root/"data"/"dukascopy_annual"/f"{p}_m1_{y}.csv.gz") for y in (2024,2025,2026)) for p in PAIRS}
    if actual!=HASHES:raise RuntimeError("HOLDOUT_VALIDATION_BLOCKED_DATA_FINGERPRINT_MISMATCH")
    out.mkdir(parents=True);archive=LocalResearchArchive(root/"data");warm=pd.Timestamp("2023-01-01",tz="UTC");end_exclusive=END+pd.Timedelta(1,unit="min");raw={p:archive.load_m1(p,warm,end_exclusive) for p in PAIRS};frames=method_a_frames(raw);events=[]
    for pair,frame in frames.items():
        entered=dedup(entry_events(frame),60);events.append(entered[(entered.event_time>=START)&(entered.event_time<=END)][["pair","event_time","residual"]])
    event_frame=pd.concat(events,ignore_index=True);observations=pd.concat([x.assign(pair=p)[["pair","time","close"]] for p,x in raw.items()],ignore_index=True);costs=load_canonical_costs(root/"config"/"cross_pair_cost_models.json");outcomes=build_event_outcomes(event_frame,observations,costs,start=START,end_exclusive=end_exclusive,holdout_authorized=True);result=evaluate_hypothesis(outcomes);conc=concentration(outcomes,result);checks=criteria(result);classification="INSUFFICIENT_HOLDOUT_SAMPLE" if not checks["C6"]["pass"] else "PROSPECTIVE_HYPOTHESIS_VALIDATED" if all(x["pass"] for x in checks.values()) else "PROSPECTIVE_HYPOTHESIS_FAILED"
    pair_results=result["pair_metrics"];population={p:{"events":int((outcomes.pair==p).sum()),"available":int(((outcomes.pair==p)&(outcomes.status=="AVAILABLE")).sum()),"missing_entry":int(((outcomes.pair==p)&(outcomes.status=="MISSING_EXACT_ENTRY")).sum()),"missing_exit":int(((outcomes.pair==p)&(outcomes.status=="MISSING_EXACT_EXIT")).sum()),"missing_path":int(((outcomes.pair==p)&(outcomes.status=="MISSING_EXACT_PATH")).sum())} for p in PAIRS};years={}
    for year in (2024,2025,2026):
        group=outcomes[pd.to_datetime(outcomes.event_time,utc=True).dt.year.eq(year)];per_pair={p:{"event_count":int(((group.pair==p)&(group.status=="AVAILABLE")).sum()),"mean_net_pips":float(group.loc[(group.pair==p)&(group.status=="AVAILABLE"),"net_directional_pips"].mean()) if ((group.pair==p)&(group.status=="AVAILABLE")).any() else None} for p in PAIRS};means=[x["mean_net_pips"] for x in per_pair.values()];years[str(year)]={"partial":year==2026,"pairs":per_pair,"equal_weight_mean_net_pips":float(np.mean(means)) if all(x is not None for x in means) else None}
    archive_hashes={p:{str(y):h for y,h in zip((2024,2025,2026),hs)} for p,hs in actual.items()};manifest={"schema_version":1,"run_id":args.run_id,"timestamp":datetime.now(UTC).isoformat(),"runner_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"hypothesis_commit":HYP_COMMIT,"hypothesis_sha256":HYP_SHA,"cost_model_sha256":COST_SHA,"archive_hashes":archive_hashes,"common_start":START.isoformat(),"common_end":END.isoformat(),"warmup_start":"2023-01-01T00:00:00+00:00","evaluation_events_pre_2024":0,"mt5":False,"broker_execution":False}
    integrity={p:{"first":pd.to_datetime(x.time,utc=True).min().isoformat(),"last":pd.to_datetime(x.time,utc=True).max().isoformat(),"rows":len(x)} for p,x in raw.items()};bootstrap=result.get("bootstrap",{"replicates":10_000,"seed":21_003,"status":"NOT_RUN_INSUFFICIENT_SAMPLE"});summary={"classification":classification,"equal_weight_aggregate_net_mean":result.get("equal_weight_mean_net_pips"),"runtime_seconds":time.perf_counter()-started,"event_count":result["event_count"]}
    documents={"manifest":manifest,"holdout_data_integrity":integrity,"event_population":population,"event_outcomes":records(outcomes),"pair_results":pair_results,"year_results":years,"bootstrap":bootstrap,"concentration":conc,"success_criteria":checks,"phase21d_summary":summary}
    for name,document in documents.items():write_json_atomic(out/f"{name}.json",clean(document))
    validation=validate(out,costs);write_json_atomic(out/"completion_validation.json",validation);print(json.dumps({"run_id":args.run_id,"classification":classification,"validation":validation}))

if __name__=="__main__":main()
