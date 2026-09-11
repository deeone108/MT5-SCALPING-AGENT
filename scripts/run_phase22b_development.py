"""Execute frozen Phase 22B v12 development on explicitly authorized 2019-2021 units."""
from __future__ import annotations
import os
for _name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[_name]="1"
import argparse, io, json, platform, re, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from jsonschema import Draft202012Validator, FormatChecker
from mt5_scalping_agent.orchestration.data_resolver import canonical_catalog_hash, guarded_load_monthly_pair_year
from mt5_scalping_agent.research.phase22b_analysis import (analyse_stage, authoritative_result_manifest, canonical_artifact_hash, development_gate_truths, deterministic_replay, non_actionable_evidence, stability_diagnostics, stratified_permutation_diagnostic)
from mt5_scalping_agent.research.phase22b_mechanism import (DATASET_ROOT_SHA256, PAIRS, SPEC_SHA256, InvalidResearchRun, build_causal_anchor_inputs_streaming, build_design_matrix, fit_wls_clustered_day, freeze_quintiles, load_frozen_spec, model_contract, prepare_model_rows)
YEARS=(2019,2020,2021)
META="governance/data_catalogs/phase22b_2019_2021_metadata.json"
LOC="governance/data_catalogs/phase22b_2019_2021_locators.json"
TASK="governance/tasks/PH22B-RI-002.json"
STATE="governance/state/project_state.json"
SPEC="research/phase22b_spec_v12.json"

def _read_json(path:Path)->dict: return json.loads(path.read_text(encoding="utf-8"))
def _expected(task:dict,path:str)->str:
    found=[x["sha256"] for x in task["inputs"] if x.get("path")==path and x.get("hash_mode")=="canonical_json"]
    if len(found)!=1: raise InvalidResearchRun(f"catalog binding missing or ambiguous: {path}")
    return str(found[0])
def _parse(payload:bytes)->pd.DataFrame:
    try: return pd.read_parquet(io.BytesIO(payload),columns=["timestamp_utc_ns","bid","ask"])
    except Exception as exc: raise InvalidResearchRun("verified parquet parse failure") from exc
def _validate_identity(value:str,n:int,name:str)->str:
    if len(value)!=n or not re.fullmatch("[0-9a-f]+",value): raise InvalidResearchRun(f"invalid {name}")
    return value
def _environment()->dict:
    return {"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__,"blas_lapack":np.__config__.CONFIG,"threads":{k:os.environ[k] for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")},"pythonhashseed":os.environ.get("PYTHONHASHSEED")}
def _schema_shape(root:Path,result:dict,schema_name:str="RESULT_MANIFEST.schema.json")->None:
    schema=_read_json(root/"governance"/schema_name)
    errors=sorted(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(result),key=lambda item:list(item.absolute_path))
    if errors: raise InvalidResearchRun("result schema failure: "+"; ".join(error.message for error in errors))
def _atomic_pair(first_path:Path,first:dict,second_path:Path,second:dict)->None:
    first_path.parent.mkdir(parents=True,exist_ok=True);second_path.parent.mkdir(parents=True,exist_ok=True)
    if first_path.exists() or second_path.exists(): raise InvalidResearchRun("immutable publication target already exists")
    staged=[];published=[]
    try:
        for path,value in ((first_path,first),(second_path,second)):
            tmp=path.with_suffix(path.suffix+".tmp")
            if tmp.exists(): raise InvalidResearchRun("stale publication staging file exists")
            tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
            staged.append((tmp,path))
        for tmp,path in staged:
            os.replace(tmp,path);published.append(path)
    except Exception:
        for path in published:
            if path.exists(): path.unlink()
        raise
    finally:
        for tmp,_ in staged:
            if tmp.exists(): tmp.unlink()
def _build_rows(root:Path,state:dict,task:dict,byte_reader)->tuple[pd.DataFrame,dict]:
    meta_path,loc_path=root/META,root/LOC
    expected_meta,expected_loc=_expected(task,META),_expected(task,LOC)
    meta_loader=lambda:_read_json(meta_path);loc_loader=lambda:_read_json(loc_path)
    prepared=[];provenance=[];frozen={}
    exposure=load_frozen_spec(root/SPEC)["implementation_determinism_v7"]["authorized_phase22a_boundary_artifact"]["spread_dislocation_quintiles"]
    for pair in PAIRS:
        tick_chunks=[]
        for year in YEARS:
            ticks,units=guarded_load_monthly_pair_year(state=state,task=task,year=year,pair=pair,metadata_catalog_loader=meta_loader,locator_catalog_loader=loc_loader,metadata_catalog_sha256=expected_meta,locator_catalog_sha256=expected_loc,byte_reader=byte_reader,parser=_parse)
            tick_chunks.append(ticks[["timestamp_utc_ns","bid","ask","source_row_ordinal"]]);provenance.extend(units)
        all_anchors=build_causal_anchor_inputs_streaming(tick_chunks,pair=pair,output_start=pd.Timestamp("2019-01-01T00:00:00Z"),output_end=pd.Timestamp("2022-01-01T00:00:00Z"))
        all_anchors["year"]=pd.to_datetime(all_anchors.anchor_utc_ns,unit="ns",utc=True).dt.year
        causal_attrition={name:int((all_anchors.causal_failure==name).sum()) for name in ("current_quote_freshness","future_quote_freshness","spread_baseline")}
        eligible=all_anchors.loc[all_anchors.causal_failure.isna()].copy()
        finite_mask=(eligible.baseline_quote_count>0)&np.isfinite(eligible[["mid","future_mid_60s","spread_pips","trailing_median_spread_pips","recent_micro_volatility_pips","impulse_15s_pips","baseline_micro_volatility_pips"]]).all(axis=1)
        preprocessing_excluded=int((~finite_mask).sum())
        eligible=eligible.loc[finite_mask].copy()
        eligible["quote_activity_ratio"]=eligible.recent_quote_count/(eligible.baseline_quote_count/4.0)
        eligible["impulse_abs_pips"]=eligible.impulse_15s_pips.abs()
        boundaries={"vol_q":freeze_quintiles(eligible.recent_micro_volatility_pips),"activity_q":freeze_quintiles(eligible.quote_activity_ratio),"impulse_abs_q":freeze_quintiles(eligible.impulse_abs_pips),"trailing_spread_q":freeze_quintiles(eligible.trailing_median_spread_pips)}
        fixed=float(np.median(eligible.spread_pips.to_numpy(np.float64)))
        rows=prepare_model_rows(eligible,pair=pair,exposure_boundaries=exposure[pair],control_boundaries=boundaries,fixed_discovery_spread_pips=fixed)
        rows["year"]=pd.to_datetime(rows.anchor_utc_ns,unit="ns",utc=True).dt.year
        rows["source_row_ordinal"]=np.arange(len(rows),dtype=np.int64)
        prepared.append(rows);frozen[pair]={"control_boundaries":{k:list(v) for k,v in boundaries.items()},"fixed_discovery_spread_pips":fixed,"anchor_count":int(len(all_anchors)),"causal_attrition":causal_attrition,"preprocessing_excluded":preprocessing_excluded,"eligible_anchor_count":int(len(eligible))}
    return pd.concat(prepared,ignore_index=True),{"catalogs":{META:expected_meta,LOC:expected_loc},"monthly_units":provenance,"frozen_development":frozen}
def _analyse(rows:pd.DataFrame,spec:dict)->dict:
    stage=analyse_stage(rows,spec)
    diagnostics=stability_diagnostics(rows,spec=spec)
    gates=development_gate_truths(stage,diagnostics)
    m4=model_contract(spec,"M4")
    def statistic(sample):
        x,y,w,names=build_design_matrix(sample,m4);return fit_wls_clustered_day(x,y,w,names,sample["utc_day"]).coefficient("exposure__WIDE")
    observed=statistic(rows)
    permutation=stratified_permutation_diagnostic(rows,statistic,observed=observed)
    return {"stage":stage,"stability":diagnostics,"development_gates":gates,"permutation":permutation}
def execute(args:argparse.Namespace,*,byte_reader=None)->dict:
    root=args.repository.resolve();task=_read_json(root/TASK);state=_read_json(root/STATE);spec=load_frozen_spec(root/SPEC)
    if task["required_spec_hash"]!=SPEC_SHA256 or state["research_spec_hash"]!=SPEC_SHA256 or task["required_dataset_hash"]!=DATASET_ROOT_SHA256: raise InvalidResearchRun("authority binding mismatch")
    if args.control_plane_only:return {"status":"CONTROL_PLANE_VALIDATED_NO_DATA_READ","specification_hash":SPEC_SHA256,"catalog_hashes":{META:_expected(task,META),LOC:_expected(task,LOC)},"years":list(YEARS),"pairs":list(PAIRS)}
    run_id=args.run_id
    if not re.fullmatch(r"phase22b_[0-9]{8}T[0-9]{6}Z",run_id): raise InvalidResearchRun("invalid run id")
    code=_validate_identity(args.code_version,40,"code version")
    reader=byte_reader or (lambda locator:Path(locator).read_bytes())
    rows,provenance=_build_rows(root,state,task,reader)
    analysis,replay_hash=deterministic_replay(lambda:_analyse(rows,spec))
    evidence=non_actionable_evidence(run_id=run_id,code_version=code,authorization_id=task["data_authorization"]["authorization_id"],stage=analysis["stage"],provenance_hashes={"dataset_root":DATASET_ROOT_SHA256,"specification":SPEC_SHA256,"metadata_catalog":_expected(task,META),"locator_catalog":_expected(task,LOC)})
    evidence["pair_stability"]=analysis["stability"]["pair"];evidence["concentration_diagnostics"]={k:v for k,v in analysis["stability"].items() if "fraction" in k};evidence["session_diagnostics"]=analysis["stability"]["session"]
    artifact={"schema_version":1,"stage":"2019-2021_RETROSPECTIVE_DEVELOPMENT","specification_sha256":SPEC_SHA256,"dataset_root_sha256":DATASET_ROOT_SHA256,"environment":_environment(),"provenance":provenance,"analysis":analysis,"evidence":evidence,"deterministic_replay_sha256":replay_hash}
    artifact_hash=canonical_artifact_hash(artifact)
    artifact["canonical_sha256"]=artifact_hash
    out=root/"reports/phase22b"/run_id/"development_artifact.json";result_path=root/"governance/results/PH22B-RI-002.json"
    now=datetime.now(timezone.utc).isoformat();result=authoritative_result_manifest(task=task,base_commit=task["base_commit"],inputs=[{"path":x["path"],"sha256":x["sha256"]} for x in task["inputs"]],artifacts=[{"path":str(out.relative_to(root)).replace('\\','/'),"sha256":artifact_hash}],commands=["python scripts/run_phase22b_development.py --run-id <UTC_ID> --code-version <HEAD_SHA>"],tests=[{"command":"deterministic replay completed byte-identically","passed":True},{"command":"PHASE22B_EVIDENCE and RESULT_MANIFEST schema validation","passed":True}],files_changed=[str(out.relative_to(root)).replace('\\','/'),"governance/results/PH22B-RI-002.json"],start_time=now,end_time=now)
    _schema_shape(root,evidence,"PHASE22B_EVIDENCE.schema.json");_schema_shape(root,result);_atomic_pair(out,artifact,result_path,result)
    return {"status":"DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW","artifact":str(out),"sha256":artifact_hash,"replay_sha256":replay_hash}
def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser();p.add_argument("--repository",type=Path,default=Path.cwd());p.add_argument("--control-plane-only",action="store_true");p.add_argument("--run-id",default="");p.add_argument("--code-version",default="");return p
def main()->int:
    try: print(json.dumps(execute(parser().parse_args()),indent=2,sort_keys=True));return 0
    except Exception as exc: print(json.dumps({"status":"PHASE_22B_INVALID_RESEARCH_RUN","error":str(exc)}),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())