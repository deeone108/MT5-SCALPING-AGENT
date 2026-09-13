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
from mt5_scalping_agent.research.phase22b_analysis import (analyse_stage, authoritative_result_manifest, canonical_artifact_hash, development_gate_truths, deterministic_replay, non_actionable_evidence, stability_diagnostics, cluster_robust_score_diagnostic)
from mt5_scalping_agent.research.phase22b_mechanism import (DATASET_ROOT_SHA256, PAIRS, SPEC_SHA256, InvalidResearchRun, build_causal_anchor_inputs_streaming, freeze_quintiles, load_frozen_spec, model_contract, prepare_model_rows)
YEARS=(2019,2020,2021)
META="governance/data_catalogs/phase22b_2019_2021_metadata.json"
LOC="governance/data_catalogs/phase22b_2019_2021_locators.json"
TASK="governance/tasks/PH22B-RI-002.json"
STATE="governance/state/project_state.json"
SPEC="research/phase22b_spec_v12.json"
BENCHMARK="governance/evidence/PH22B_V12_EXACT_BENCHMARK.json"
BENCHMARK_SHA256="7bf5c078912545645132d88ab73bf17068d8633f07acc242f56121fc3ca504c5"

def _read_json(path:Path)->dict: return json.loads(path.read_text(encoding="utf-8"))
def _expected(task:dict,path:str)->str:
    found=[x["sha256"] for x in task["inputs"] if x.get("path")==path and x.get("hash_mode")=="canonical_json"]
    if len(found)!=1: raise InvalidResearchRun(f"catalog binding missing or ambiguous: {path}")
    return str(found[0])
def _verified_benchmark(root:Path)->dict:
    path=root/BENCHMARK
    if not path.is_file(): raise InvalidResearchRun("required exact benchmark evidence absent")
    value=_read_json(path)
    if canonical_catalog_hash(value)!=BENCHMARK_SHA256: raise InvalidResearchRun("exact benchmark evidence hash mismatch")
    expected={"resamples":10000,"utc_day_blocks":1096,"coefficient_count":80,"fallback_count":100,"seed":22002,"compressed_regression_population_count":24,"non_regression_population_count":5,"deterministic_replay_analysis_passes":2,"population_count_derivation":{"M0_response_fits":4,"M4_response_fits_including_fixed_pips":5,"interaction_fits":7,"attenuation_before_after_fits":8,"pair_day_response_populations":4,"pair_day_normalization_ratio_populations":1}}
    measurements=value.get("measurements",{}); passes=value.get("passes",{})
    if (value.get("specification_sha256")!=SPEC_SHA256 or value.get("originating_implementation_commit")!="34510a47a01041a27484b8e28f54e513ad50f737" or value.get("projection_derivation_commit")!="34510a47a01041a27484b8e28f54e513ad50f737" or value.get("configuration")!=expected or measurements.get("wall_seconds")!=1082.371652300004 or measurements.get("peak_additional_rss_bytes")!=450580480 or measurements.get("equivalent_k80_regression_populations")!=7.137933540603742 or measurements.get("non_regression_equivalent_k80_populations")!=0.0029177295918367346 or measurements.get("per_pass_regression_projection_seconds")!=7725.896920350889 or measurements.get("per_pass_non_regression_conservative_bound_seconds")!=3.1580677992809423 or measurements.get("full_workload_projection_seconds")!=15458.109976300339 or measurements.get("schedule_sha256")!="3338bf2d0ebea5e6c6d95053216b6e6449b1d4d1839d3989501605d768e1910d" or value.get("data_accessed")!=[] or value.get("no_market_data_accessed") is not True or passes!={"wall_time":True,"peak_memory":True,"full_workload_projection":True,"all":True}):
        raise InvalidResearchRun("exact benchmark evidence content mismatch")
    return {"path":BENCHMARK,"canonical_sha256":BENCHMARK_SHA256,"configuration":expected,"measurements":measurements,"passes":passes,"no_market_data_accessed":True}
def _parse(payload:bytes)->pd.DataFrame:
    try: return pd.read_parquet(io.BytesIO(payload),columns=["timestamp_utc_ns","bid","ask"])
    except Exception as exc: raise InvalidResearchRun("verified parquet parse failure") from exc
def _validate_identity(value:str,n:int,name:str)->str:
    if len(value)!=n or not re.fullmatch("[0-9a-f]+",value): raise InvalidResearchRun(f"invalid {name}")
    return value

def _canonical_authorized_years(value: object, name: str) -> tuple[int, ...]:
    """Parse the repository JSON string-year contract into integer domain years."""
    if not isinstance(value, list) or not value:
        raise InvalidResearchRun(f"invalid {name}")
    years: list[int] = []
    for item in value:
        if not isinstance(item, str) or re.fullmatch(r"[1-9][0-9]{3}", item) is None:
            raise InvalidResearchRun(f"invalid {name}")
        years.append(int(item))
    if len(years) != len(set(years)):
        raise InvalidResearchRun(f"invalid {name}")
    return tuple(years)

def _fixed_discovery_spread_pips(eligible: pd.DataFrame) -> float:
    """Freeze the v12 fixed-spread denominator from positive eligible quotes only."""
    if "spread_pips" not in eligible.columns:
        raise InvalidResearchRun("eligible spread population missing")
    spread = pd.to_numeric(eligible["spread_pips"], errors="coerce").to_numpy(np.float64)
    positive = spread[np.isfinite(spread) & (spread > 0.0)]
    if positive.size == 0:
        raise InvalidResearchRun("fixed discovery spread requires eligible finite strictly-positive observations")
    fixed = float(np.median(positive))
    if not np.isfinite(fixed) or fixed <= 0.0:
        raise InvalidResearchRun("fixed discovery spread is nonpositive")
    return fixed
def _private_output_root(args:argparse.Namespace,root:Path,run_id:str,code:str)->Path:
    candidate=getattr(args,"output_root",None)
    if candidate is None: raise InvalidResearchRun("supervisor-private output root required")
    output=candidate.resolve()
    if output.name!="staging": raise InvalidResearchRun("output root is not supervisor-private staging")
    identity_path=output.parent/"identity.json"
    if not identity_path.is_file(): raise InvalidResearchRun("supervisor identity absent")
    identity=_read_json(identity_path)
    expected={"run_id":run_id,"task_id":"PH22B-RI-002","specification_hash":SPEC_SHA256,"code_commit":code,"authorized_symbols":list(PAIRS)}
    if any(identity.get(key)!=value for key,value in expected.items()): raise InvalidResearchRun("supervisor identity mismatch")
    if _canonical_authorized_years(identity.get("authorized_data_windows"), "supervisor authorized data windows") != YEARS:
        raise InvalidResearchRun("supervisor identity mismatch")
    if Path(identity.get("authoritative_binding",{}).get("repository","")).resolve()!=root: raise InvalidResearchRun("supervisor repository binding mismatch")
    return output
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
        tick_chunks=[]; global_ordinal=0
        for year in YEARS:
            ticks,units=guarded_load_monthly_pair_year(state=state,task=task,year=year,pair=pair,metadata_catalog_loader=meta_loader,locator_catalog_loader=loc_loader,metadata_catalog_sha256=expected_meta,locator_catalog_sha256=expected_loc,byte_reader=byte_reader,parser=_parse)
            ticks=ticks.copy(); ticks["source_row_ordinal"]=np.arange(global_ordinal,global_ordinal+len(ticks),dtype=np.int64); global_ordinal+=len(ticks)
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
        fixed=_fixed_discovery_spread_pips(eligible)
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
    score=cluster_robust_score_diagnostic(rows,m4)
    return {"stage":stage,"stability":diagnostics,"development_gates":gates,"score_diagnostic":score,"diagnostic_provenance":{"method":"frozen_v9_cluster_robust_score","role":"SUPPORTING_ROBUSTNESS_DIAGNOSTIC_ONLY_NON_GATING","included_in_advancement_or_fdr":False,"canonical_sha256":score["canonical_sha256"]}}
def execute(args:argparse.Namespace,*,byte_reader=None)->dict:
    root=args.repository.resolve();task=_read_json(root/TASK);state=_read_json(root/STATE);spec=load_frozen_spec(root/SPEC);benchmark=_verified_benchmark(root)
    if task["required_spec_hash"]!=SPEC_SHA256 or state["research_spec_hash"]!=SPEC_SHA256 or task["required_dataset_hash"]!=DATASET_ROOT_SHA256: raise InvalidResearchRun("authority binding mismatch")
    if args.control_plane_only:return {"status":"CONTROL_PLANE_VALIDATED_NO_DATA_READ","specification_hash":SPEC_SHA256,"catalog_hashes":{META:_expected(task,META),LOC:_expected(task,LOC)},"years":list(YEARS),"pairs":list(PAIRS),"benchmark_evidence":benchmark}
    run_id=args.run_id
    if not re.fullmatch(r"phase22b_[0-9]{8}T[0-9]{6}Z",run_id): raise InvalidResearchRun("invalid run id")
    code=_validate_identity(args.code_version,40,"code version")
    publication_root=_private_output_root(args,root,run_id,code)
    reader=byte_reader or (lambda locator:Path(locator).read_bytes())
    rows,provenance=_build_rows(root,state,task,reader)
    analysis,replay_hash=deterministic_replay(lambda:_analyse(rows,spec))
    evidence=non_actionable_evidence(run_id=run_id,code_version=code,authorization_id=task["data_authorization"]["authorization_id"],stage=analysis["stage"],provenance_hashes={"dataset_root":DATASET_ROOT_SHA256,"specification":SPEC_SHA256,"metadata_catalog":_expected(task,META),"locator_catalog":_expected(task,LOC),"implementation_benchmark":BENCHMARK_SHA256})
    evidence["pair_stability"]=analysis["stability"]["pair"];evidence["concentration_diagnostics"]={k:v for k,v in analysis["stability"].items() if "fraction" in k};evidence["session_diagnostics"]=analysis["stability"]["session"]
    artifact={"schema_version":1,"stage":"2019-2021_RETROSPECTIVE_DEVELOPMENT","specification_sha256":SPEC_SHA256,"dataset_root_sha256":DATASET_ROOT_SHA256,"environment":_environment(),"provenance":{**provenance,"implementation_benchmark":benchmark},"analysis":analysis,"evidence":evidence,"deterministic_replay_sha256":replay_hash}
    artifact_hash=canonical_artifact_hash(artifact)
    artifact["canonical_sha256"]=artifact_hash
    artifact_relative=f"reports/phase22b/{run_id}/development_artifact.json"
    result_relative="governance/results/PH22B-RI-002.json"
    out=publication_root/artifact_relative;result_path=publication_root/result_relative
    now=datetime.now(timezone.utc).isoformat();result=authoritative_result_manifest(task=task,base_commit=task["base_commit"],inputs=[{"path":x["path"],"sha256":x["sha256"]} for x in task["inputs"]],artifacts=[{"path":artifact_relative,"sha256":artifact_hash}],commands=["python scripts/run_phase22b_development.py --run-id <UTC_ID> --code-version <HEAD_SHA>"],tests=[{"command":"deterministic replay completed byte-identically","passed":True},{"command":"PHASE22B_EVIDENCE and RESULT_MANIFEST schema validation","passed":True}],files_changed=[artifact_relative,result_relative],start_time=now,end_time=now)
    _schema_shape(root,evidence,"PHASE22B_EVIDENCE.schema.json");_schema_shape(root,result);_atomic_pair(out,artifact,result_path,result)
    return {"status":"DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW","artifact":str(out),"sha256":artifact_hash,"replay_sha256":replay_hash}
def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser();p.add_argument("--repository",type=Path,default=Path.cwd());p.add_argument("--control-plane-only",action="store_true");p.add_argument("--run-id",default="");p.add_argument("--code-version",default="");p.add_argument("--output-root",type=Path,default=None);return p
def main()->int:
    try: print(json.dumps(execute(parser().parse_args()),indent=2,sort_keys=True));return 0
    except Exception as exc: print(json.dumps({"status":"PHASE_22B_INVALID_RESEARCH_RUN","error":str(exc)}),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
