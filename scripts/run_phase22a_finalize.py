"""Finalize Phase 22A diagnostics for frozen 2023 survivors only."""
import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
import numpy as np, pandas as pd
from run_phase22a_inference import candidates, json_default
SPEC="11581b33dcd0616d25ad39cc2de37db6e4bbba62e49ea1d283b1a3449d988323"
DATA="ae0f5b70f686c1b0fff05c0b71f9efb7c3d5da4983eba0df895989dbf6572a91"

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def sessions(hours):
 return {"asian":hours<8,"london":(hours>=8)&(hours<16),"new_york":(hours>=13)&(hours<21),"overlap":(hours>=13)&(hours<16)}
def add(acc,cid,dim,label,values,groups,kind):
 mask=np.isfinite(values)
 for lab in np.unique(label[mask]):
  m=mask&(label==lab)
  if kind.startswith("contrast"):
   for g in (-1,1):
    x=values[m&(groups==g)]; acc[cid,dim,str(lab),g][0]+=float(np.nansum(x)); acc[cid,dim,str(lab),g][1]+=int(np.isfinite(x).sum())
  else:
   x=values[m]; acc[cid,dim,str(lab),0][0]+=float(np.nansum(x)); acc[cid,dim,str(lab),0][1]+=int(np.isfinite(x).sum())
def finalize(run):
 d=json.loads((run/"discovery_survivors.json").read_text()); c=json.loads((run/"confirmation_survivors.json").read_text()); h=json.loads((run/"holdout_survivors.json").read_text())
 registry={x["id"]:x for x in candidates()}; selected=h["survivors"]; acc=defaultdict(lambda:[0.0,0])
 for path in sorted((run/"anchors/internal_holdout").rglob("*.parquet")):
  pair=path.parts[-3]; year=path.parts[-2]; month=path.parts[-1][:2]; frame=pd.read_parquet(path); ts=pd.to_datetime(frame.anchor_utc_ns,utc=True); hour=ts.dt.hour.to_numpy(); weekday=ts.dt.day_name().str[:3].to_numpy()
  spread_reg=np.digitize(frame.spread_dislocation.to_numpy(),d["thresholds"][pair]["spread_dislocation"])+1
  vol_reg=np.digitize(frame.volatility_15s.to_numpy(),d["thresholds"][pair]["volatility_15s"])+1
  for cid in selected:
   x=registry[cid]; bins=np.digitize(frame[x["feature"]].to_numpy(),d["thresholds"][pair][x["feature"]])+1; future=frame[f"future_change_{x['h']}s_spread"].to_numpy(); kind=x["kind"]
   if kind=="signed": chosen=(bins==1)|(bins==5); values=np.sign(frame[x["feature"]].to_numpy())*future; groups=np.zeros(len(frame),int)
   elif kind=="high_signed": chosen=bins==5; values=np.sign(frame[x["direction"]].to_numpy())*future; groups=np.zeros(len(frame),int)
   else:
    chosen=(bins==1)|(bins==5); groups=np.where(bins==5,1,-1); values=np.abs(future) if kind=="contrast_abs" else frame[f"future_spread_normalization_{x['h']}s"].to_numpy()
   values=np.where(chosen,values,np.nan)
   for dim,label in (("pair",np.full(len(frame),pair)),("year",np.full(len(frame),year)),("month",np.full(len(frame),month)),("weekday",weekday),("spread_quintile",spread_reg),("micro_volatility_quintile",vol_reg)): add(acc,cid,dim,label,values,groups,kind)
   for name,mask in sessions(hour).items(): add(acc,cid,"session",np.where(mask,name,"__exclude__"),values,groups,kind)
 diagnostics={}
 for cid in selected:
  dims={}
  for dim in ("pair","year","month","weekday","session","spread_quintile","micro_volatility_quintile"):
   vals={}
   labels=sorted({k[2] for k in acc if k[0]==cid and k[1]==dim and k[2]!="__exclude__"})
   for label in labels:
    if registry[cid]["kind"].startswith("contrast"):
     hi=acc[cid,dim,label,1]; lo=acc[cid,dim,label,-1]; vals[label]=(hi[0]/hi[1]-lo[0]/lo[1]) if hi[1] and lo[1] else None
    else:
     z=acc[cid,dim,label,0]; vals[label]=z[0]/z[1] if z[1] else None
   dims[dim]=vals
  direction=d["results"][cid]["direction"]; pair_vals=dims["pair"]; month_vals=dims["month"]
  pair_share=max(abs(v) for v in pair_vals.values())/sum(abs(v) for v in pair_vals.values()) if pair_vals else 1
  month_share=max(abs(v) for v in month_vals.values())/sum(abs(v) for v in month_vals.values()) if month_vals else 1
  top5=h["results"][cid]["top5_day_absolute_share"]
  diagnostics[cid]={"dimensions":dims,"frozen_direction":direction,"pair_direction_count":sum(np.sign(v)==direction for v in pair_vals.values()),"concentration":{"largest_pair_absolute_share":pair_share,"largest_month_absolute_share":month_share,"top5_day_absolute_share":top5,"pass":pair_share<.5 and month_share<.5 and top5<.5}}
 robust=[cid for cid in selected if diagnostics[cid]["concentration"]["pass"]]
 ranked=sorted(robust,key=lambda cid:abs(h["results"][cid]["effect_spread_units"]),reverse=True)
 def cls(cid):
  e=abs(h["results"][cid]["effect_spread_units"])
  return "POTENTIALLY_RESEARCH_WORTHY" if e>=.25 else "MICROSTRUCTURALLY_INTERESTING" if e>=.10 else "STATISTICALLY_DETECTABLE"
 shortlist=[{"candidate_id":cid,"family":h["results"][cid]["family"],"lookback_seconds":h["results"][cid]["lookback_seconds"],"horizon_seconds":h["results"][cid]["horizon_seconds"],"direction":h["results"][cid]["frozen_discovery_direction"],"discovery_effect_spread_units":d["results"][cid]["effect_spread_units"],"confirmation_effect_spread_units":c["results"][cid]["effect_spread_units"],"holdout_effect_spread_units":h["results"][cid]["effect_spread_units"],"holdout_effect_pips":h["results"][cid]["effect_pips"],"pair_coverage":diagnostics[cid]["pair_direction_count"],"practical_relevance":cls(cid),"concentration":diagnostics[cid]["concentration"],"session_stability":diagnostics[cid]["dimensions"]["session"]} for cid in ranked]
 lineage={"discovery":digest(run/"discovery_survivors.json"),"confirmation":digest(run/"confirmation_survivors.json"),"holdout":digest(run/"holdout_survivors.json")}
 manifests={name:json.loads((run/f"{name}_anchor_manifest.json").read_text()) for name in ("discovery","confirmation","internal_holdout")}
 leakage={"spec_hash_pinned":all(x["spec_sha256"]==SPEC for x in manifests.values()),"dataset_root_pinned":all(x["dataset_root"]==DATA for x in manifests.values()),"partition_years_exact":set(int(k.split('_')[1]) for k in manifests["discovery"]["units"])=={2019,2020,2021} and set(int(k.split('_')[1]) for k in manifests["confirmation"]["units"])=={2022} and set(int(k.split('_')[1]) for k in manifests["internal_holdout"]["units"])=={2023},"thresholds_reused":c["thresholds_reused_unchanged"] and h["thresholds_reused_unchanged"],"directions_reused":c["directions_reused_unchanged"] and h["directions_reused_unchanged"],"no_2024_artifacts":not any("2024" in str(p) for p in (run/"anchors").rglob("*.parquet"))}
 classification="PHASE_22A_ROBUST_PHENOMENON_FOUND" if robust else ("PHASE_22A_WEAK_OR_UNSTABLE_PHENOMENA" if selected else "PHASE_22A_NO_ROBUST_MICROSTRUCTURE_FOUND")
 payload={"classification":classification,"run_id":run.name,"spec_sha256":SPEC,"dataset_root":DATA,"lineage":lineage,"eligible_anchors":{k:v["eligible_anchors"] for k,v in manifests.items()},"candidate_families":sorted({x["family"] for x in registry.values()}),"counts":{"evaluated_discovery":len(d["results"]),"survived_discovery":len(d["survivors"]),"survived_confirmation":len(c["survivors"]),"survived_holdout":len(h["survivors"]),"robust_after_concentration":len(robust)},"leakage_validation":leakage,"diagnostics":diagnostics,"ranked_shortlist":shortlist,"prohibitions":{"2024_plus_access":False,"strategy":False,"pnl":False,"optimization":False,"machine_learning":False,"order_api":False,"broker_execution":False}}
 content=(json.dumps(payload,indent=2,default=json_default)+"\n").encode(); out=run/"final_report.json";out.write_bytes(content);(run/"final_report.sha256").write_bytes((hashlib.sha256(content).hexdigest()+"\n").encode());print(json.dumps({"classification":classification,"robust":len(robust),"sha256":hashlib.sha256(content).hexdigest()}))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--run-id",default="phase22a_20260909T220000Z");p.add_argument("--report-root",type=Path,default=Path("reports/phase22a"));a=p.parse_args();finalize(a.report_root/a.run_id)