"""Frozen Phase 21B descriptive mechanism reproduction; no strategy, PnL, execution, or MT5."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,time
from datetime import UTC,datetime
from pathlib import Path
import numpy as np
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.cross_pair_edge_discovery import USD_SIGN,causal_bars,pip_size,benjamini_hochberg
from mt5_scalping_agent.research.relative_value_discovery import common_residuals,entry_events,dedup
from mt5_scalping_agent.research.convergence_mechanism import contribution_arithmetic,mechanism_labels,adverse_path_metrics,target_excursions,trading_day_bootstrap
from mt5_scalping_agent.research.manifest import fingerprint_files,local_archive_dataset,sha256_value,write_json_atomic
from mt5_scalping_agent.research.phase21b_completion import apply_fdr,block_median_distribution,classify,coefficient_drift,concentration as concentration_report,day_delta_distribution,mechanism_summary as frozen_summary,method_test,pairwise_test,residual_volatility_stability,stability_test,validate_run
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_phase21a_reproduction import rolling_ols_residuals
PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD'); H=(5,10,15,30,60); OFF=np.arange(5,61,5); EPS=1e-10; REQUIRED=('mechanism_by_horizon','target_movement','common_movement','joint_mechanism','contribution_fractions','path_geometry','adverse_widening','target_mfe_mae','pairwise_decomposition','one_leg_economics','two_leg_economics','year_analysis','leave_one_year_out','session_analysis','volatility_analysis','extremeness_analysis','concentration','bootstrap','fdr','method_b','relationship_stability')
def rec(x): return json.loads(x.to_json(orient='records',date_format='iso'))
def val(x): return None if pd.isna(x) else float(x)
def summary(g):
 c=g.mechanism.value_counts(); n=len(g); return {'n':n,**{f'p_{k.lower()}':float(c.get(k,0)/n) if n else None for k in ('TARGET_REVERSAL','COMMON_CATCH_UP','BOTH_CONTRIBUTE','NEITHER_OR_AMBIGUOUS','NON_CONVERGENT')},'delta':float((c.get('TARGET_REVERSAL',0)-c.get('COMMON_CATCH_UP',0))/n) if n else None}
def stats(g,cols):
 out={**cols,'n':len(g)}
 for c in ('target_contribution','common_contribution','remainder','target_fraction','common_fraction','remainder_fraction'):
  x=g[c].dropna(); out[c]={'mean':val(x.mean()),'median':val(x.median()),'p25':val(x.quantile(.25)),'p75':val(x.quantile(.75))}
 return out
def delta_boot(g,seed):
 obs=summary(g)['delta']; x=g.assign(day=pd.to_datetime(g.event_time,utc=True).dt.date); table=x.groupby('day').mechanism.value_counts().unstack(fill_value=0); total=table.sum(1).to_numpy(float); target=table.get('TARGET_REVERSAL',pd.Series(0,index=table.index)).to_numpy(float); common=table.get('COMMON_CATCH_UP',pd.Series(0,index=table.index)).to_numpy(float); rng=np.random.default_rng(seed); b=np.empty(5000)
 for start in range(0,5000,250):
  ix=rng.integers(len(table),size=(min(250,5000-start),len(table))); b[start:start+len(ix)]=(target[ix].sum(1)-common[ix].sum(1))/total[ix].sum(1)
 return {'n':len(g),'effect':obs,'ci95':[float(np.quantile(b,.025)),float(np.quantile(b,.975))],'p_value_target':float((b<=0).mean()),'p_value_common':float((b>=0).mean()),'samples':5000,'seed':seed}
def block_medians(frame,column,seed):
 x=frame[['event_time',column]].dropna().copy(); days=pd.to_datetime(x.event_time,utc=True).dt.date; unique=sorted(days.unique()); mapping={d:i for i,d in enumerate(unique)}; codes=days.map(mapping).to_numpy(); values=x[column].to_numpy(float); order=np.argsort(values); values=values[order]; codes=codes[order]; rng=np.random.default_rng(seed); result=np.empty(5000)
 for start in range(0,5000,100):
  size=min(100,5000-start); draws=rng.integers(len(unique),size=(size,len(unique))); counts=np.zeros((size,len(unique)),dtype=np.int16)
  for i in range(size): counts[i]=np.bincount(draws[i],minlength=len(unique))
  weights=counts[:,codes]; cumulative=np.cumsum(weights,axis=1); totals=cumulative[:,-1]; lo=(totals-1)//2+1; hi=totals//2+1; ilo=(cumulative>=lo[:,None]).argmax(1); ihi=(cumulative>=hi[:,None]).argmax(1); result[start:start+size]=(values[ilo]+values[ihi])/2
 return result
def fdr(rows,key='p_value'):
 use=[r for r in rows if r.get(key) is not None]; a=benjamini_hochberg([r[key] for r in use]); return [{**r,**z} for r,z in zip(use,a,strict=True)]
def grouped(events,keys): return [{**dict(zip(keys,k if isinstance(k,tuple) else (k,),strict=True)),**summary(g)} for k,g in events.groupby(keys,dropna=False,observed=True)]
def rolling_ols_details(wide,target):
 columns=[p for p in PAIRS if p!=target]; joined=wide[[target,*columns]].dropna(); v=joined.to_numpy(float); x=np.column_stack((np.ones(len(v)),v[:,1:])); y=v[:,0]; residual=pd.Series(np.nan,index=wide.index); betas=pd.DataFrame(np.nan,index=wide.index,columns=columns)
 if len(v)<=5760:return residual,betas
 xtx=x[:5760].T@x[:5760]; xty=x[:5760].T@y[:5760]; out=np.full(len(v),np.nan); coefficients=np.full((len(v),3),np.nan)
 for i in range(5760,len(v)):
  beta=np.linalg.pinv(xtx,hermitian=True)@xty; out[i]=y[i]-x[i]@beta; coefficients[i]=beta[1:]; old=x[i-5760]; xtx+=np.outer(x[i],x[i])-np.outer(old,old); xty+=x[i]*y[i]-old*y[i-5760]
 residual.loc[joined.index]=out; betas.loc[joined.index]=coefficients; return residual,betas
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--run-id',required=True); a=ap.parse_args(); start=time.perf_counter(); root=Path('.').resolve(); out=root/'reports/phase21b'/a.run_id
 if out.exists(): raise RuntimeError('run directory exists')
 out.mkdir(parents=True); spec=root/'docs/PHASE_21B_RESEARCH_SPEC.md'; costp=root/'config/cross_pair_cost_models.json'; commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(); now=datetime.now(UTC)
 archive=LocalResearchArchive(root/'data'); raw={p:archive.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}
 if any((pd.to_datetime(x.time,utc=True)>=pd.Timestamp(DEVELOPMENT_END)).any() for x in raw.values()): raise RuntimeError('2024+ detected')
 datasets={p:local_archive_dataset(archive_root=root/'data',archive=archive,symbol=p,periods=[(DEVELOPMENT_START,DEVELOPMENT_END)],project_root=root) for p in PAIRS}; costs=json.loads(costp.read_text())['models']
 codefiles=fingerprint_files([Path(__file__),root/'src/mt5_scalping_agent/research/convergence_mechanism.py',root/'src/mt5_scalping_agent/research/relative_value_discovery.py'],root)
 meta={'schema_version':1,'run_id':a.run_id,'run_timestamp':now.isoformat(),'git_commit':commit,'parent_phase21a_run_id':'reproduction_20260903T224000Z_860ce89','phase21b_specification_hash':'sha256:'+hashlib.sha256(spec.read_bytes()).hexdigest(),'research_period':{'start':DEVELOPMENT_START.isoformat(),'end_exclusive':DEVELOPMENT_END.isoformat()},'data_hashes':{p:d['identifier'] for p,d in datasets.items()},'cost_model_hash':'sha256:'+hashlib.sha256(costp.read_bytes()).hexdigest(),'code_hash':sha256_value(codefiles),'safety':{'mt5':False,'strategy':False,'pnl':False,'execution':False,'post_2023':False}}
 def clean(x):
  if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
  if isinstance(x,(list,tuple)): return [clean(v) for v in x]
  if isinstance(x,np.generic): return clean(x.item())
  if isinstance(x,(pd.Timestamp,datetime)): return x.isoformat()
  if isinstance(x,float) and not np.isfinite(x): return None
  return x
 def emit(n,p): write_json_atomic(out/f'{n}.json',clean({**meta,'component':n,'payload':p}))
 frames=common_residuals(raw); prices={p:causal_bars(raw[p],5).set_index('completed_time').close for p in PAIRS}; wide=pd.DataFrame({p:f.set_index('event_time').z for p,f in frames.items()})
 allrows=[]; paths=[]; populations=[]; pairrows=[]
 for pair,full in frames.items():
  full=full.set_index('event_time'); ev=dedup(entry_events(full.reset_index())); populations.append({'pair':pair,'events':len(ev)}); times=full.index; pos=times.get_indexer(pd.DatetimeIndex(ev.event_time)); r=full.residual.to_numpy(); z=full.z.to_numpy(); common=full.common.to_numpy(); close=prices[pair].reindex(times).to_numpy(); future=np.column_stack([times.get_indexer(times[pos]+pd.Timedelta(minutes=int(h))) for h in OFF]); validf=future>=0; complete=validf.all(1); rp=np.full(future.shape,np.nan); zp=rp.copy(); cp=rp.copy(); pp=rp.copy(); rp[validf]=r[future[validf]]; zp[validf]=z[future[validf]]; cp[validf]=common[future[validf]]; pp[validf]=close[future[validf]]
  adv=adverse_path_metrics(r[pos],rp,OFF); direction=-np.sign(r[pos])*USD_SIGN[pair]; exc=target_excursions(close[pos],pp,direction,pip_size(pair),OFF)
  ratio=np.abs(rp)/np.abs(r[pos])[:,None]
  def first(mask): return np.where(complete&mask.any(1),OFF[mask.argmax(1)],np.nan)
  cross=(rp==0)|(np.sign(rp)!=np.sign(r[pos])[:,None]); widen=np.maximum(np.abs(rp)-np.abs(r[pos])[:,None],0); imax=np.argmax(np.where(np.isfinite(widen),widen,-np.inf),1)
  for i,e in enumerate(ev.itertuples()):
   paths.append({'event_id':f'{pair}:{pd.Timestamp(e.event_time).isoformat()}','pair':pair,'event_time':e.event_time,'initial_residual':r[pos[i]],**{f'residual_{h}m':rp[i,j] for j,h in enumerate(OFF) if h in H},'time_to_75':val(first(ratio<=.75)[i]),'time_to_50':val(first(ratio<=.5)[i]),'time_to_25':val(first(ratio<=.25)[i]),'zero_cross_time':val(first(cross)[i]),'maximum_widening':val(widen[i,imax[i]]) if complete[i] else None,'time_to_maximum_widening':int(OFF[imax[i]]) if complete[i] else None,'no_50pct_convergence_within_60m':bool(np.isnan(first(ratio<=.5)[i])),'widening_ratio':val(adv['widening_ratio'][i]),'max_pre_convergence_widening':val(adv['max_pre_convergence_widening'][i]),'time_to_worst_widening':val(adv['time_to_worst_widening'][i])})
   for j,h in enumerate(OFF):
    if h not in H or future[i,j]<0: continue
    d,t,c,rem=contribution_arithmetic([r[pos[i]]],[rp[i,j]],[zp[i,j]-z[pos[i]]],[cp[i,j]-common[pos[i]]]); mech=mechanism_labels(d,t,c)[0]; D=d[0]; native_moves=direction[i]*(pp[i,:j+1]-close[pos[i]])/pip_size(pair); i_mfe=int(np.nanargmax(native_moves)); i_mae=int(np.nanargmin(native_moves))
    row={'event_id':f'{pair}:{pd.Timestamp(e.event_time).isoformat()}','pair':pair,'event_time':e.event_time,'year':int(e.year),'session':e.session,'volatility_regime':('LOW' if e.vol<.3 else 'NORMAL' if e.vol<.7 else 'HIGH' if e.vol<.9 else 'EXTREME'),'bucket':e.bucket,'horizon':int(h),'initial_residual':r[pos[i]],'future_residual':rp[i,j],'reduction':D,'target_standardised_change':zp[i,j]-z[pos[i]],'common_component_change':cp[i,j]-common[pos[i]],'target_contribution':t[0],'common_contribution':c[0],'remainder':rem[0],'mechanism':mech,'target_native_price_change':pp[i,j]-close[pos[i]],'target_pip_change':(pp[i,j]-close[pos[i]])/pip_size(pair),'mfe_pips':np.nanmax(native_moves),'mae_pips':np.nanmin(native_moves),'time_to_mfe':OFF[i_mfe],'time_to_mae':OFF[i_mae],'mfe_before_mae':i_mfe<i_mae,'mae_before_mfe':i_mae<i_mfe,'target_fraction':t[0]/D if D>0 else np.nan,'common_fraction':c[0]/D if D>0 else np.nan,'remainder_fraction':rem[0]/D if D>0 else np.nan}; allrows.append(row)
    for contributor in PAIRS:
     if contributor==pair: continue
     dz=wide[contributor].reindex([times[future[i,j]]]).iloc[0]-wide[contributor].reindex([times[pos[i]]]).iloc[0]; pc0=prices[contributor].reindex([times[pos[i]]]).iloc[0]; pch=prices[contributor].reindex([times[future[i,j]]]).iloc[0]; target_usd=direction[i]*100000*(pp[i,j]-close[pos[i]])/close[pos[i]]; contributor_usd=np.sign(r[pos[i]])*USD_SIGN[contributor]*100000*(pch-pc0)/pc0; base_usd=100000*(float(costs[pair]['base']['round_trip_cost_pips'])*pip_size(pair)/close[pos[i]])+100000*(float(costs[contributor]['base']['round_trip_cost_pips'])*pip_size(contributor)/pc0); stress_usd=100000*(float(costs[pair]['stress']['round_trip_cost_pips'])*pip_size(pair)/close[pos[i]])+100000*(float(costs[contributor]['stress']['round_trip_cost_pips'])*pip_size(contributor)/pc0); pairrows.append({'event_id':row['event_id'],'target_pair':pair,'contributor_pair':contributor,'event_time':e.event_time,'horizon':int(h),'convergent':bool(D>0),'target_contribution':t[0],'contributor_contribution':np.sign(r[pos[i]])*dz/3,'favourable_relative_movement_usd':max(target_usd+contributor_usd,0),'combined_BASE_cost_usd':base_usd,'combined_STRESS_cost_usd':stress_usd,'stress_multiple_two_leg':max(target_usd+contributor_usd,0)/stress_usd})
 events=pd.DataFrame(allrows); pathdf=pd.DataFrame(paths); pairs=pd.DataFrame(pairrows); primary=events[events.horizon.eq(60)]
 mechanisms=[{**{'pair':p,'horizon':int(h)},**summary(g)} for (p,h),g in events.groupby(['pair','horizon'])]; target=rec(events.groupby(['pair','horizon']).agg(n=('target_contribution','size'),mean_standardised_change=('target_standardised_change','mean'),mean_contribution=('target_contribution','mean'),median_native_pips=('target_pip_change','median')).reset_index()); commonout=rec(events.groupby(['pair','horizon']).agg(n=('common_contribution','size'),mean_change=('common_component_change','mean'),mean_contribution=('common_contribution','mean')).reset_index()); fractions=[stats(g,{'pair':p,'horizon':int(h)}) for (p,h),g in events.groupby(['pair','horizon'])]
 b1=[]; b2=[]
 for (p,h),g in events.groupby(['pair','horizon']):
  q=delta_boot(g,21022+H.index(h)); q.update({'pair':p,'horizon':int(h)}); direction='target' if q['effect']>=0 else 'common'; q['p_value']=q['p_value_target'] if direction=='target' else q['p_value_common']; q['direction']=direction; (b1 if h==60 else b2).append(q)
 b1=fdr(b1); b2=fdr(b2); aggregate=summary(primary)
 # Descriptive path risk and economics; family tests use frozen one-sided median screens.
 adverse=[]; b3=[]; economics=[]; b4=[]
 for p,g in pathdf.groupby('pair'):
  x=g.widening_ratio.dropna(); adverse.append({'pair':p,'n':len(x),'median':val(x.median()),'p75':val(x.quantile(.75)),'p90':val(x.quantile(.9)),'p95':val(x.quantile(.95)),'p99':val(x.quantile(.99)),**{f'p_gt_{k}':float((x>k).mean()) for k in (.1,.25,.5,1)}}); boot=block_medians(g,'widening_ratio',21100); b3.append({'pair':p,'n':len(x),'effect':val(x.median()),'ci95':[val(np.quantile(boot,.025)),val(np.quantile(boot,.975))],'p_value':float((boot>.25).mean())})
  e=primary[(primary.pair==p)&(primary.mechanism=='TARGET_REVERSAL')].copy(); stress=float(costs[p]['stress']['round_trip_cost_pips']); base=float(costs[p]['base']['round_trip_cost_pips']); e['stress_multiple']=e.mfe_pips/stress; economics.append({'pair':p,'n':len(e),'median_favourable_pips':val(e.mfe_pips.median()),'median_adverse_pips':val(e.mae_pips.median()),'median_base_multiple':val((e.mfe_pips/base).median()),'median_stress_multiple':val(e.stress_multiple.median()),**{f'p_ge_{k}x_stress':float((e.stress_multiple>=k).mean()) if len(e) else None for k in (1,2,4,6,8)}}); boot=block_medians(e,'stress_multiple',21200) if len(e) else np.array([]); b4.append({'pair':p,'n':len(e),'effect':val(e.stress_multiple.median()),'ci95':[val(np.quantile(boot,.025)),val(np.quantile(boot,.975))] if len(boot) else [None,None],'p_value':float((boot<2).mean()) if len(boot) else None})
 b3=fdr(b3); b4=[{'pair':r0['pair'],'n':r0['n'],'median_stress_multiple':r0['effect'],'CI':r0['ci95'],'raw_p':r0['p_value'],'bootstrap_replicates':5000,'BH_q':r0['q_value'],'FDR_survival':r0['survives_fdr'],'B4A_pass':r0['survives_fdr'] and r0['effect']>=2} for r0 in fdr(b4)]
 years=grouped(primary,['pair','year']); loo=[]
 for p,g in primary.groupby('pair'):
  for y in range(2019,2024): loo.append({'pair':p,'excluded_year':y,**summary(g[g.year!=y])})
 sessions=grouped(primary,['pair','session']); volatility=grouped(primary,['pair','volatility_regime']); extreme=grouped(primary,['pair','bucket'])
 pairsummary=[]; b5raw=[]; primary_direction='target' if aggregate['delta']>=.1 else 'common' if aggregate['delta']<=-.1 else 'descriptive'
 for (ta,co),g in pairs[pairs.horizon.eq(60)].groupby(['target_pair','contributor_pair']):
  result=pairwise_test(g,primary_direction if primary_direction!='descriptive' else 'target',21400+PAIRS.index(ta)*4+PAIRS.index(co)); result.update({'target_pair':ta,'contributor_pair':co}); pairsummary.append(result)
  if primary_direction!='descriptive': b5raw.append(result)
 b5=apply_fdr(b5raw) if b5raw else []
 unordered=[]
 pairs['unordered_pair']=pairs.apply(lambda x:'-'.join(sorted((x.target_pair,x.contributor_pair))),axis=1)
 for name,g in pairs[(pairs.horizon==60)&pairs.convergent].groupby('unordered_pair'):
  diff=g.target_contribution-g.contributor_contribution; unordered.append({'unordered_pair':name,'N':len(g),'mean_pairwise_delta':float(((diff>EPS).sum()-(diff < -EPS).sum())/len(g)),'qualitatively_weak_or_mixed':bool(abs(((diff>EPS).sum()-(diff < -EPS).sum())/len(g))<.1)})
 b4braw=[]
 for name,g in pairs[pairs.horizon.eq(60)].groupby('unordered_pair'):
  boot=block_median_distribution(g,'stress_multiple_two_leg',21500+len(b4braw)); med=float(g.stress_multiple_two_leg.median()); row={'unordered_pair':name,'N':len(g),'median_stress_multiple':med,'P_ge_1x':float((g.stress_multiple_two_leg>=1).mean()),'P_ge_2x':float((g.stress_multiple_two_leg>=2).mean()),'P_ge_4x':float((g.stress_multiple_two_leg>=4).mean()),'CI':[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],'raw_p':float((boot<2).mean()),'bootstrap_replicates':5000}; b4braw.append(row)
 b4b=apply_fdr(b4braw)
 for r0 in b4b:r0['economic_pass']=r0['FDR_survival'] and r0['median_stress_multiple']>=2 and r0['P_ge_1x']>=.6 and r0['P_ge_2x']>=.5 and r0['P_ge_4x']>=.25
 mfe=[]
 for (p,h),g in events.groupby(['pair','horizon']):
  mfe.append({'pair':p,'horizon':int(h),'N_eligible':len(g),'N_unavailable':int(populations[[x['pair'] for x in populations].index(p)]['events']-len(g)),**{f'MFE_{q}':val(getattr(g.mfe_pips,q)()) for q in ('mean','median')},'MFE_p25':val(g.mfe_pips.quantile(.25)),'MFE_p75':val(g.mfe_pips.quantile(.75)),'MFE_p90':val(g.mfe_pips.quantile(.9)),**{f'MAE_{q}':val(getattr(g.mae_pips,q)()) for q in ('mean','median')},'MAE_p25':val(g.mae_pips.quantile(.25)),'MAE_p75':val(g.mae_pips.quantile(.75)),'MAE_p90':val(g.mae_pips.quantile(.9)),'MFE_before_MAE_rate':float(g.mfe_before_mae.mean()),'MAE_before_MFE_rate':float(g.mae_before_mfe.mean()),'median_time_to_MFE':val(g.time_to_mfe.median()),'median_time_to_MAE':val(g.time_to_mae.median()),'status':'AVAILABLE'})
 conc=[{'pair':p,'mechanism':concentration_report(g,'target_contribution'),'path':concentration_report(pathdf[pathdf.pair==p],'widening_ratio'),'economics':concentration_report(g.assign(stress_multiple=g.mfe_pips/float(costs[p]['stress']['round_trip_cost_pips'])),'stress_multiple')} for p,g in primary.groupby('pair')]
 methodb=[]; method_frames={}; methodb_rel=[]
 for p in PAIRS:
  rb,beta=rolling_ols_details(wide,p); f=frames[p][['event_time','session','vol','bucket','year']].copy(); f['residual']=rb.reindex(pd.DatetimeIndex(f.event_time)).to_numpy(); f['abs_residual']=f.residual.abs(); from mt5_scalping_agent.research.relative_value_discovery import causal_percentile_valid,bucket as buck,outcomes; f['residual_percentile']=causal_percentile_valid(f.abs_residual,5760); f['bucket']=buck(f.residual_percentile); ev=dedup(entry_events(outcomes(f))); full=f.set_index('event_time'); idx=full.index; p0=idx.get_indexer(pd.DatetimeIndex(ev.event_time)); ph=idx.get_indexer(pd.DatetimeIndex(ev.event_time)+pd.Timedelta(minutes=60)); ok=(p0>=0)&(ph>=0); d=np.abs(full.residual.to_numpy()[p0[ok]])-np.abs(full.residual.to_numpy()[ph[ok]]); dz=wide[p].reindex(idx[ph[ok]]).to_numpy()-wide[p].reindex(idx[p0[ok]]).to_numpy(); dr=full.residual.to_numpy()[ph[ok]]-full.residual.to_numpy()[p0[ok]]; dc=dz-dr; _,tc,cc,_=contribution_arithmetic(full.residual.to_numpy()[p0[ok]],full.residual.to_numpy()[ph[ok]],dz,dc); labels=mechanism_labels(d,tc,cc); tmp=pd.DataFrame({'event_time':idx[p0[ok]],'mechanism':labels}); method_frames[p]=tmp; methodb.append({'pair':p,**frozen_summary(tmp)}); cd=coefficient_drift(beta); rv=residual_volatility_stability(rb,pd.DatetimeIndex(rb.index)); methodb_rel.append({'pair':p,**cd,'residual_stability':rv,'pass':cd['coefficient_pass'] and rv['pass']})
 b7raw=[]
 for p in PAIRS:
  row=method_test(primary[primary.pair==p],method_frames[p],21600+PAIRS.index(p)); row['pair']=p; b7raw.append(row)
 b7=apply_fdr(b7raw)
 for r0 in b7:r0['pair_pass']=r0['method_difference']<.1 and r0['FDR_survival'] and r0['category_match']
 b7pass=sum(r0['pair_pass'] for r0 in b7)>=3 and not any((r0['delta_A']*r0['delta_B']<0 and abs(r0['delta_B'])>=.1) for r0 in b7)
 delta_primary=aggregate['delta']; primary_category=frozen_summary(primary)['dominant']; b6raw=[]
 groups=[]
 for y,g in primary.groupby('year'):groups.append(('year',str(y),g))
 for y in range(2019,2024):groups.append(('leave_one_year_out',str(y),primary[primary.year!=y]))
 for n,g in primary.groupby('session'):groups.append(('session',str(n),g))
 for n,g in primary.groupby('volatility_regime'):groups.append(('volatility',str(n),g))
 for i,(typ,name,g) in enumerate(groups):
  row=stability_test(g,delta_primary,primary_category,21700+i); row.update({'group_type':typ,'group_name':name}); b6raw.append(row)
 b6=apply_fdr(b6raw)
 for r0 in b6:r0['group_pass']=r0['FDR_survival'] and not r0['category_changed']
 def rate(t):
  x=[r0 for r0 in b6 if r0['group_type']==t]; return sum(r0['group_pass'] for r0 in x),len(x)
 yr,yn=rate('year'); lo,ln=rate('leave_one_year_out'); se,sn=rate('session'); vo,vn=rate('volatility'); b6pass=yr>=4 and lo==5 and se/sn>=.75 and vo/vn>=.75
 methoda_rel=[]
 for p,f in frames.items(): methoda_rel.append({'pair':p,**residual_volatility_stability(f.residual,pd.DatetimeIndex(f.event_time))})
 relationship_pass=all(r0['pass'] for r0 in methoda_rel) and b6pass and sum(r0['pass'] for r0 in methodb_rel)>=3
 b1pass=abs(delta_primary)>=.1 and all(r0['survives_fdr'] and r0['direction']==('target' if delta_primary>0 else 'common') for r0 in b1)
 b3pass=all(r0.get('FDR_survival',r0.get('survives_fdr',False)) and r0['effect']<=.25 and next(x for x in adverse if x['pair']==r0['pair'])['p90']<=1 and next(x for x in adverse if x['pair']==r0['pair'])['p_gt_1']<=.1 for r0 in b3)
 for r0 in b4:r0['B4A_pass']=r0['FDR_survival'] and r0['median_stress_multiple']>=2 and next(x for x in economics if x['pair']==r0['pair'])['p_ge_1x_stress']>=.6 and next(x for x in economics if x['pair']==r0['pair'])['p_ge_2x_stress']>=.5 and next(x for x in economics if x['pair']==r0['pair'])['p_ge_4x_stress']>=.25
 pairwise_pass=sum(bool(x['mean_pairwise_delta']>0) for x in unordered)>=4 and not any(r0['FDR_survival'] and r0['observed_pairwise_delta']<=-.1 for r0 in b5)
 proportions=frozen_summary(primary)['proportions']; evidence={'complete':True,'prospective':False,'delta':delta_primary,'b1_pass':b1pass,'b6_pass':b6pass,'relationship_pass':relationship_pass,'proportions':proportions}; base_class=classify(evidence); economic_pass=all(r0['B4A_pass'] for r0 in b4) if base_class=='TARGET_REVERSAL_PHENOMENON' else all(r0['economic_pass'] for r0 in b4b); prospective=base_class in ('TARGET_REVERSAL_PHENOMENON','COMMON_CATCH_UP_PHENOMENON','MIXED_CONVERGENCE_PHENOMENON') and (b1pass or base_class=='MIXED_CONVERGENCE_PHENOMENON') and b6pass and all(x['mechanism']['top10_event']<=.1 for x in conc) and b3pass and economic_pass and pairwise_pass and b7pass and relationship_pass; evidence['prospective']=prospective; classification=classify(evidence)
 payloads={'mechanism_by_horizon':mechanisms,'target_movement':target,'common_movement':commonout,'joint_mechanism':mechanisms,'contribution_fractions':fractions,'path_geometry':rec(pathdf),'adverse_widening':adverse,'target_mfe_mae':mfe,'pairwise_decomposition':{'ordered':pairsummary,'unordered':unordered},'one_leg_economics':economics,'two_leg_economics':b4b,'year_analysis':years,'leave_one_year_out':loo,'session_analysis':sessions,'volatility_analysis':volatility,'extremeness_analysis':extreme,'concentration':conc,'bootstrap':{'B1':b1,'B2':b2,'B3':b3,'B4A':b4,'B4B':b4b,'B5':b5,'B6':b6,'B7':b7},'fdr':{'B1':b1,'B2':b2,'B3':b3,'B4A':b4,'B4B':b4b,'B5':b5,'B6':b6,'B7':b7},'method_b':methodb,'relationship_stability':{'overall_pass':relationship_pass,'method_a':methoda_rel,'method_b':methodb_rel},'b4a_one_leg_economics':{'tests':b4,'overall_pass':all(r0['B4A_pass'] for r0 in b4)},'b4b_two_leg_economics':{'tests':b4b,'overall_pass':all(r0['economic_pass'] for r0 in b4b)},'b5_pairwise_attribution':{'tests':b5,'unordered':unordered,'overall_pass':pairwise_pass},'b6_regime_stability':{'tests':b6,'year_pass':[yr,yn],'leave_one_out_pass':[lo,ln],'session_pass':[se,sn],'volatility_pass':[vo,vn],'overall_pass':b6pass},'b7_method_b_robustness':{'tests':b7,'overall_pass':b7pass},'method_a_relationship_stability':{'pairs':methoda_rel,'overall_pass':all(r0['pass'] for r0 in methoda_rel) and b6pass},'method_b_relationship_stability':{'pairs':methodb_rel,'overall_pass':sum(r0['pass'] for r0 in methodb_rel)>=3},'trading_day_concentration':conc}
 missing=[]; status=classification
 emit('manifest',{**meta,'datasets':datasets,'code_files':codefiles,'event_population':populations,'required_components':list(REQUIRED)}); [emit(k,v) for k,v in payloads.items()]
 summary_payload={'status':status,'classification':classification,'classification_evidence':evidence,'missing_components':missing,'runtime_seconds':time.perf_counter()-start,'event_population':populations,'aggregate_60m':aggregate,'B1':b1,'B3':b3,'B4A':b4,'B4B':b4b,'B5':b5,'B6':payloads['b6_regime_stability'],'B7':payloads['b7_method_b_robustness'],'path_risk':adverse,'economics':economics,'method_b':methodb}; emit('phase21b_summary',summary_payload)
 validation=validate_run(out,a.run_id,meta['phase21b_specification_hash']); validation['classification_recomputed']=classify(evidence); validation['valid']=validation['valid'] and validation['classification_recomputed']==classification; emit('completion_validation',validation); print(out/'phase21b_summary.json')
if __name__=='__main__': main()
