"""Frozen Phase 21B completion, inference, and semantic validation primitives."""
from __future__ import annotations
from collections.abc import Callable,Mapping,Sequence
import json,math
from pathlib import Path
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.cross_pair_edge_discovery import benjamini_hochberg
PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD'); HORIZONS=(5,10,15,30,60); SAMPLES=5000; EPS=1e-10

def day_delta_distribution(frame:pd.DataFrame,positive:str,negative:str,seed:int,samples:int=SAMPLES)->np.ndarray:
 x=frame.assign(_day=pd.to_datetime(frame.event_time,utc=True).dt.date); tab=x.groupby('_day').mechanism.value_counts().unstack(fill_value=0); total=tab.sum(1).to_numpy(float); pos=tab.get(positive,pd.Series(0,index=tab.index)).to_numpy(float); neg=tab.get(negative,pd.Series(0,index=tab.index)).to_numpy(float); rng=np.random.default_rng(seed); out=np.empty(samples)
 for start in range(0,samples,250):
  n=min(250,samples-start); ix=rng.integers(len(tab),size=(n,len(tab))); out[start:start+n]=(pos[ix].sum(1)-neg[ix].sum(1))/total[ix].sum(1)
 return out

def block_median_distribution(frame:pd.DataFrame,column:str,seed:int,samples:int=SAMPLES)->np.ndarray:
 x=frame[['event_time',column]].dropna(); days=pd.to_datetime(x.event_time,utc=True).dt.date; unique=sorted(days.unique()); ids=pd.Series(days).map({d:i for i,d in enumerate(unique)}).to_numpy(); values=x[column].to_numpy(float); order=np.argsort(values); values=values[order]; ids=ids[order]; rng=np.random.default_rng(seed); out=np.empty(samples)
 for start in range(0,samples,100):
  n=min(100,samples-start); draws=rng.integers(len(unique),size=(n,len(unique))); counts=np.zeros((n,len(unique)),np.int16)
  for i in range(n): counts[i]=np.bincount(draws[i],minlength=len(unique))
  cum=np.cumsum(counts[:,ids],axis=1); totals=cum[:,-1]; lo=(totals-1)//2+1; hi=totals//2+1; il=(cum>=lo[:,None]).argmax(1); ih=(cum>=hi[:,None]).argmax(1); out[start:start+n]=(values[il]+values[ih])/2
 return out

def apply_fdr(rows:Sequence[dict])->list[dict]:
 rows=list(rows); adjusted=benjamini_hochberg([float(x['raw_p']) for x in rows]); return [{**r,'BH_q':a['q_value'],'FDR_survival':a['survives_fdr']} for r,a in zip(rows,adjusted,strict=True)]

def mechanism_summary(frame:pd.DataFrame)->dict:
 n=len(frame); c=frame.mechanism.value_counts(); props={k:float(c.get(k,0)/n) for k in ('TARGET_REVERSAL','COMMON_CATCH_UP','BOTH_CONTRIBUTE','NEITHER_OR_AMBIGUOUS','NON_CONVERGENT')}; return {'N':n,'proportions':props,'delta':props['TARGET_REVERSAL']-props['COMMON_CATCH_UP'],'dominant':max(props,key=props.get) if n else None}

def pairwise_test(frame:pd.DataFrame,direction:str,seed:int)->dict:
 x=frame[frame.convergent].copy(); diff=x.target_contribution-x.contributor_contribution; x['mechanism']=np.where(diff>EPS,'TARGET',np.where(diff < -EPS,'CONTRIBUTOR','TIE')); observed=float(((diff>EPS).sum()-(diff < -EPS).sum())/len(x)); boot=day_delta_distribution(x,'TARGET','CONTRIBUTOR',seed); raw=float((boot<=0).mean()) if direction=='target' else float((boot>=0).mean()); return {'N':len(x),'direction_tested':direction,'observed_pairwise_delta':observed,'bootstrap_CI':[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],'raw_p':raw,'bootstrap_replicates':len(boot),'ties':int((np.abs(diff)<=EPS).sum()),'qualitative_sign':'TARGET' if observed>EPS else 'CONTRIBUTOR' if observed < -EPS else 'TIE'}

def stability_test(frame:pd.DataFrame,delta_primary:float,primary_category:str,seed:int)->dict:
 s=mechanism_summary(frame); boot=day_delta_distribution(frame,'TARGET_REVERSAL','COMMON_CATCH_UP',seed); deviation=np.abs(boot-delta_primary); return {**s,'delta_primary':delta_primary,'stability_deviation':abs(s['delta']-delta_primary),'CI':[float(np.quantile(deviation,.025)),float(np.quantile(deviation,.975))],'raw_p':float((deviation>=.10).mean()),'bootstrap_replicates':len(boot),'category_changed':s['dominant']!=primary_category}

def method_test(a:pd.DataFrame,b:pd.DataFrame,seed:int)->dict:
 sa,sb=mechanism_summary(a),mechanism_summary(b); ba=day_delta_distribution(a,'TARGET_REVERSAL','COMMON_CATCH_UP',seed); bb=day_delta_distribution(b,'TARGET_REVERSAL','COMMON_CATCH_UP',seed+1); n=min(len(ba),len(bb)); dist=np.abs(bb[:n]-ba[:n]); return {'N':min(len(a),len(b)),'delta_A':sa['delta'],'delta_B':sb['delta'],'method_difference':abs(sb['delta']-sa['delta']),'Method_A_category':sa['dominant'],'Method_B_category':sb['dominant'],'CI':[float(np.quantile(dist,.025)),float(np.quantile(dist,.975))],'raw_p':float((dist>=.10).mean()),'bootstrap_replicates':n,'category_match':sa['dominant']==sb['dominant']}

def residual_volatility_stability(residual:pd.Series,times:pd.DatetimeIndex)->dict:
 x=pd.Series(np.asarray(residual,float),index=times).dropna(); ref=float(x.std()); ratios={str(y):float(v/ref) for y,v in x.groupby(x.index.year).std().items()}; return {'full_residual_volatility':ref,'annual_ratios':ratios,'pass':len(ratios)==5 and all(.5<=v<=2 for v in ratios.values())}

def coefficient_drift(coefficients:pd.DataFrame)->dict:
 rows=[]; passes=[]
 for name,x in coefficients.items():
  x=x.dropna(); reference=float(x.median()); drift=(x-reference).abs()/max(abs(reference),.10); reversal=float((np.sign(x)!=np.sign(reference)).mean()); row={'contributor':name,'reference_beta':reference,'median_absolute_relative_drift':float(drift.median()),'p90_absolute_relative_drift':float(drift.quantile(.9)),'sign_reversal_proportion':reversal,'by_year':[{'year':int(y),'median_beta':float(g.median()),'median_relative_drift':float(((g-reference).abs()/max(abs(reference),.10)).median())} for y,g in x.groupby(x.index.year)]}; row['pass']=row['median_absolute_relative_drift']<=.25 and row['p90_absolute_relative_drift']<=.5 and reversal<=.1; rows.append(row); passes.append(row['pass'])
 return {'coefficients':rows,'coefficient_pass':all(passes)}

def concentration(frame:pd.DataFrame,column:str)->dict:
 x=frame[['event_time',column]].dropna().copy(); x['_abs']=x[column].abs(); total=x._abs.sum()
 def shares(key):
  z=x.groupby(key)._abs.sum().sort_values(ascending=False); return {'largest':float(z.iloc[0]/total),'top5':float(z.head(5).sum()/total),'top10':float(z.head(10).sum()/total)}
 t=pd.to_datetime(x.event_time,utc=True); return {'N':len(x),'year':shares(t.dt.year),'month':shares(t.dt.strftime('%Y-%m')),'trading_day':shares(t.dt.date),'top5_event':float(x._abs.nlargest(5).sum()/total),'top10_event':float(x._abs.nlargest(10).sum()/total)}

def classify(e:Mapping[str,object])->str:
 if not e.get('complete'): return 'PHASE_21B_INCOMPLETE'
 if e.get('prospective'): return 'HUMAN_GATE_REQUIRED_PROSPECTIVE_HYPOTHESIS'
 d=float(e['delta']); b1=bool(e['b1_pass']); b6=bool(e['b6_pass']); rel=bool(e['relationship_pass']); p=dict(e['proportions']); mixed=p['BOTH_CONTRIBUTE']==max(p.values()) or (abs(d)<.1 and p['TARGET_REVERSAL']+p['COMMON_CATCH_UP']+p['BOTH_CONTRIBUTE']>=.4) or (p['BOTH_CONTRIBUTE']+p['NEITHER_OR_AMBIGUOUS']+p['NON_CONVERGENT']>=.6 and p['BOTH_CONTRIBUTE']>=max(p['TARGET_REVERSAL'],p['COMMON_CATCH_UP']))
 if d>=.1 and b1 and b6: return 'TARGET_REVERSAL_PHENOMENON'
 if d<=-.1 and b1 and b6: return 'COMMON_CATCH_UP_PHENOMENON'
 if mixed:return 'MIXED_CONVERGENCE_PHENOMENON'
 if abs(d)>=.1 and (not b6 or not rel):return 'MECHANISM_UNSTABLE'
 return 'NO_ACTIONABLE_MECHANISM'

def validate_run(directory:Path,run_id:str,spec_hash:str)->dict:
 required=('manifest','mechanism_by_horizon','target_movement','common_movement','joint_mechanism','contribution_fractions','path_geometry','adverse_widening','target_mfe_mae','pairwise_decomposition','one_leg_economics','two_leg_economics','year_analysis','leave_one_year_out','session_analysis','volatility_analysis','extremeness_analysis','concentration','bootstrap','fdr','method_b','relationship_stability','b4a_one_leg_economics','b4b_two_leg_economics','b5_pairwise_attribution','b6_regime_stability','b7_method_b_robustness','method_a_relationship_stability','method_b_relationship_stability','trading_day_concentration'); missing=[]; invalid=[]
 for name in required:
  p=directory/f'{name}.json'
  if not p.exists():missing.append(name);continue
  try: doc=json.loads(p.read_text())
  except Exception:invalid.append(f'{name}:json');continue
  if doc.get('schema_version')!=1 or doc.get('run_id')!=run_id or doc.get('phase21b_specification_hash')!=spec_hash:invalid.append(f'{name}:provenance')
  if doc.get('research_period',{}).get('end_exclusive')!='2024-01-01T00:00:00+00:00':invalid.append(f'{name}:period')
  if 'payload' not in doc:invalid.append(f'{name}:payload')
 text=''.join(p.read_text() for p in directory.glob('*.json')); 
 if 'NaN' in text or 'Infinity' in text:invalid.append('nonfinite')
 return {'valid':not missing and not invalid,'missing_components':missing,'invalid_components':invalid,'warnings':[]}