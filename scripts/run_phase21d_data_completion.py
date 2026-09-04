"""Validate and fingerprint Phase 21D raw holdout archives without signal analysis."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from datetime import UTC,datetime
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research.manifest import write_json_atomic

PAIRS=("EURUSD","GBPUSD","USDJPY","USDCAD");YEARS=(2024,2025,2026)
LIMIT=pd.Timestamp("2026-08-21T20:59:00Z");EUR_BEFORE={2024:"99c121ed88da5f749e2104ae5623429431465c0b66c4ce866a2e705a00e317b8",2025:"7d00cf38c5886ad7a09a2bc8cf0a0407fa29869c99fe9161da9a5f5971957312",2026:"3f19f01d56bbce1038fe29a7ca3e88364a6afa9f9a07e7fd6375b7329e6e4b50"}
REQUIRED=("manifest","archive_inventory","archive_hashes","pair_integrity","cross_pair_coverage")

def fingerprint(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect_archive(path:Path,pair:str,year:int)->dict[str,object]:
    malformed=0
    try:frame=pd.read_csv(path,compression="gzip")
    except Exception as error:return {"pair":pair,"year":year,"path":str(path),"exists":True,"parses":False,"error":str(error)}
    required={"time","open","high","low","close","tick_volume"};missing=sorted(required-set(frame.columns));parsed=pd.to_datetime(frame.get("time"),utc=True,errors="coerce");malformed=int(parsed.isna().sum());valid_times=parsed.dropna();duplicate=int(valid_times.duplicated().sum());monotonic=bool(valid_times.is_monotonic_increasing);numeric=frame[[c for c in ("open","high","low","close") if c in frame]].apply(pd.to_numeric,errors="coerce");nonpositive=int((numeric<=0).any(axis=1).sum()) if len(numeric.columns)==4 else None;ohlc_invalid=int(((numeric.high<numeric.low)|(numeric.high<numeric.open)|(numeric.high<numeric.close)|(numeric.low>numeric.open)|(numeric.low>numeric.close)).sum()) if len(numeric.columns)==4 else None
    validation_error=None
    try:validate_ohlcv(frame.assign(time=parsed))
    except Exception as error:validation_error=str(error)
    gaps=valid_times.diff().dropna();large=gaps[gaps>pd.Timedelta(1,unit="min")]
    return {"pair":pair,"year":year,"path":str(path),"exists":True,"parses":True,"sha256":fingerprint(path),"rows":len(frame),"first_timestamp":valid_times.min().isoformat() if len(valid_times) else None,"last_timestamp":valid_times.max().isoformat() if len(valid_times) else None,"timezone":"UTC" if str(valid_times.dtype).endswith("UTC]") else str(valid_times.dtype),"missing_columns":missing,"malformed_timestamps":malformed,"monotonic":monotonic,"duplicate_timestamps":duplicate,"nonpositive_price_rows":nonpositive,"ohlc_invalid_rows":ohlc_invalid,"schema_validation_error":validation_error,"gaps_over_one_minute":len(large),"maximum_gap_minutes":float(large.max()/pd.Timedelta(1,unit="min")) if len(large) else 0.}

def validate_completion(inventory:list[dict[str,object]],coverage:dict[str,object])->dict[str,object]:
    failures=[];expected={(p,y) for p in PAIRS for y in YEARS};found={(x.get("pair"),x.get("year")) for x in inventory if x.get("exists")}
    if found!=expected:failures.append("missing_pair_year_archives")
    for item in inventory:
        if not item.get("parses") or item.get("missing_columns") or item.get("malformed_timestamps") or not item.get("monotonic") or item.get("duplicate_timestamps") or item.get("nonpositive_price_rows") or item.get("ohlc_invalid_rows") or item.get("schema_validation_error"):failures.append(f"integrity:{item.get('pair')}:{item.get('year')}")
        if item.get("last_timestamp") and pd.Timestamp(item["last_timestamp"])>LIMIT:failures.append(f"beyond_authorized_boundary:{item.get('pair')}:{item.get('year')}")
    if not coverage.get("common_start") or not coverage.get("common_end") or pd.Timestamp(coverage["common_end"])>LIMIT:failures.append("invalid_common_coverage")
    return {"valid":not failures,"classification":"HOLDOUT_DATA_READY" if not failures else "HOLDOUT_DATA_INCOMPLETE","failures":failures,"all_four_pairs":found==expected,"all_required_years":found==expected,"raw_rows_sufficient_to_attempt_phase21d":not failures}

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--run-id",required=True);args=parser.parse_args();root=Path(".").resolve();out=root/"reports"/"phase21d_data_completion"/args.run_id
    if out.exists():raise RuntimeError("immutable run directory already exists")
    out.mkdir(parents=True);inventory=[]
    for pair in PAIRS:
        for year in YEARS:
            path=root/"data"/"dukascopy_annual"/f"{pair}_m1_{year}.csv.gz"
            inventory.append(inspect_archive(path,pair,year) if path.exists() else {"pair":pair,"year":year,"path":str(path),"exists":False})
    pair_integrity={pair:{"rows":sum(int(x.get("rows",0)) for x in inventory if x["pair"]==pair),"start":min(x["first_timestamp"] for x in inventory if x["pair"]==pair and x.get("first_timestamp")),"end":max(x["last_timestamp"] for x in inventory if x["pair"]==pair and x.get("last_timestamp")),"annual_files_valid":all(x.get("parses") and not x.get("schema_validation_error") for x in inventory if x["pair"]==pair)} for pair in PAIRS}
    coverage={"pairs":{p:{"start":v["start"],"end":v["end"],"rows":v["rows"]} for p,v in pair_integrity.items()},"common_start":max(v["start"] for v in pair_integrity.values()),"common_end":min(v["end"] for v in pair_integrity.values()),"selection_basis":"raw archive availability only"};validation=validate_completion(inventory,coverage);eur_after={str(y):next(x["sha256"] for x in inventory if x["pair"]=="EURUSD" and x["year"]==y) for y in YEARS};manifest={"schema_version":1,"run_id":args.run_id,"timestamp":datetime.now(UTC).isoformat(),"git_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"purpose":"raw Dukascopy holdout data completion only","authorized_end":LIMIT.isoformat(),"eurusd_before":{str(k):v for k,v in EUR_BEFORE.items()},"eurusd_after":eur_after,"eurusd_unchanged":eur_after=={str(k):v for k,v in EUR_BEFORE.items()},"signals_calculated":False,"events_generated":False,"performance_calculated":False,"mt5":False}
    documents={"manifest":manifest,"archive_inventory":{"files":inventory},"archive_hashes":{"files":[{k:x[k] for k in ("pair","year","path","rows","first_timestamp","last_timestamp","sha256")} for x in inventory]},"pair_integrity":pair_integrity,"cross_pair_coverage":coverage,"completion_validation":validation}
    for name,document in documents.items():write_json_atomic(out/f"{name}.json",document)
    print(json.dumps({"run_id":args.run_id,**validation}))

if __name__=="__main__":main()
