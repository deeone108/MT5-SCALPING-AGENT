"""Clean, provenance-complete reproduction of frozen Phase 21A."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,time
from datetime import UTC,datetime
from pathlib import Path
import numpy as np
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.convergence_mechanism import path_metrics
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_END,DEVELOPMENT_START
from mt5_scalping_agent.research.manifest import fingerprint_files,local_archive_dataset,sha256_value,write_json_atomic
from mt5_scalping_agent.research.relative_value_discovery import BUCKETS,bootstrap_difference,bucket,causal_percentile_valid,common_residuals,dedup,entry_events,fdr,outcomes

PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD'); HORIZONS=(5,10,15,30,60); WINDOW=20*24*12
def records(frame): return json.loads(frame.to_json(orient='records',date_format='iso'))
def rolling_ols_residuals(wide,target):
    columns=[p for p in PAIRS if p!=target]; joined=wide[[target,*columns]].dropna(); values=joined.to_numpy(float); result=pd.Series(np.nan,index=wide.index)
    if len(values)<=WINDOW:return result
    x=np.column_stack((np.ones(len(values)),values[:,1:])); y=values[:,0]; xtx=x[:WINDOW].T@x[:WINDOW]; xty=x[:WINDOW].T@y[:WINDOW]
    output=np.full(len(values),np.nan)
    for i in range(WINDOW,len(values)):
        output[i]=y[i]-x[i]@np.linalg.pinv(xtx,hermitian=True)@xty
        old=x[i-WINDOW]; xtx+=np.outer(x[i],x[i])-np.outer(old,old); xty+=x[i]*y[i]-old*y[i-WINDOW]
    result.loc[joined.index]=output; return result
def summarize(events):
    rows=[]
    for pair,g in events.groupby('pair'):
        for h in HORIZONS:
            valid=g[f'outcome_{h}m_status'].eq('AVAILABLE'); x=g.loc[valid]
            rows.append({'pair':pair,'horizon_minutes':h,'events':len(g),'valid_endpoints':int(valid.sum()),'missing_exact_endpoints':int((~valid).sum()),'mean_absolute_residual_change':float(x[f'change_{h}m'].mean()),'median_magnitude_ratio':float(x[f'ratio_{h}m'].median()),'signed_persistence_probability':float(x[f'sign_persistence_{h}m'].mean()),'zero_cross_probability':float(x[f'zero_cross_{h}m'].mean()),'convergence_probability':float((x[f'change_{h}m']<0).mean())})
    return rows
def grouped(events,keys):
    return records(events.groupby(keys,dropna=False).change_60m.agg(['count','mean','median']).reset_index())
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--run-id',required=True); args=parser.parse_args()
    started=time.perf_counter(); root=Path('.').resolve(); out=root/'reports/phase21a'/args.run_id
    if out.exists(): raise RuntimeError('run directory already exists')
    out.mkdir(parents=True); now=datetime.now(UTC); commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    spec=root/'docs/PHASE_21A_RESEARCH_SPEC.md'; cost=root/'config/cross_pair_cost_models.json'
    archive=LocalResearchArchive(root/'data'); raw={p:archive.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}
    if any((f.time>=pd.Timestamp(DEVELOPMENT_END)).any() for f in raw.values()): raise RuntimeError('post-2023 timestamp detected')
    datasets={p:local_archive_dataset(archive_root=root/'data',archive=archive,symbol=p,periods=[(DEVELOPMENT_START,DEVELOPMENT_END)],project_root=root) for p in PAIRS}
    code_files=fingerprint_files([Path(__file__),root/'src/mt5_scalping_agent/research/relative_value_discovery.py',root/'src/mt5_scalping_agent/research/convergence_mechanism.py',root/'src/mt5_scalping_agent/research/time_alignment.py'],root)
    meta={'schema_version':1,'run_id':args.run_id,'run_timestamp':now.isoformat(),'completion_status':'COMPLETED','evidence_role':'CORRECTED_PHASE_21A_REPRODUCTION','research_period':{'start':DEVELOPMENT_START.isoformat(),'end_exclusive':DEVELOPMENT_END.isoformat()},'git_commit':commit,'specification_hash':'sha256:'+hashlib.sha256(spec.read_bytes()).hexdigest(),'code_hash':sha256_value(code_files),'data_hashes':{p:d['identifier'] for p,d in datasets.items()},'cost_model_hash':'sha256:'+hashlib.sha256(cost.read_bytes()).hexdigest()}
    def emit(name,payload): write_json_atomic(out/f'{name}.json',{**meta,'payload':payload})
    method_a={p:outcomes(f) for p,f in common_residuals(raw).items()}; events=[]; populations=[]
    for p,f in method_a.items():
        entries=entry_events(f); selected=dedup(entries); selected['pair']=p; events.append(selected)
        counts=entries.bucket.value_counts(); populations.append({'pair':p,'valid_residual_observations':int(f.residual.notna().sum()),'valid_causal_residual_percentiles':int(f.residual_percentile.notna().sum()),'entries_90_95':int(counts.get('90-95',0)),'entries_95_99':int(counts.get('95-99',0)),'entries_99_100':int(counts.get('99-100',0)),'total_extreme_entries':len(entries),'deduplicated_events':len(selected)})
    events=pd.concat(events,ignore_index=True); primary=summarize(events)
    tests=[]
    for p,g in events.groupby('pair'):
        test=bootstrap_difference(g,'change_60m',g.bucket.isin(['95-99','99-100']),samples=5000,seed=21021); test.update({'pair':p,'horizon_minutes':60,'effect_size':test.get('mean')}); tests.append(test)
    tests=fdr(tests)
    path_rows=[]
    for p,g in events.groupby('pair'):
        full=method_a[p].reset_index(drop=True); timeline=pd.DatetimeIndex(full.event_time); pos=timeline.get_indexer(pd.DatetimeIndex(g.event_time)); metrics=path_metrics(full.residual.to_numpy(),timeline,pos)
        valid=metrics['valid']; initial=full.residual.to_numpy()[pos]; _,endpoint_positions=__import__('mt5_scalping_agent.research.time_alignment',fromlist=['exact_positions']).exact_positions(timeline,timeline[pos],HORIZONS); path_values=np.full(endpoint_positions.shape,np.nan); path_values[endpoint_positions>=0]=full.residual.to_numpy()[endpoint_positions[endpoint_positions>=0]]; zero=np.where((path_values==0)|(np.sign(path_values)!=np.sign(initial)[:,None]),np.array(HORIZONS),np.nan); first_zero=np.where(np.isfinite(zero).any(1),np.nanmin(zero,axis=1),np.nan)
        path_rows.append({'pair':p,'events':len(g),'complete_paths':int(valid.sum()),'missing_paths':int((~valid).sum()),'median_time_to_75_minutes':float(np.nanmedian(metrics['time_to_75'])),'median_time_to_50_minutes':float(np.nanmedian(metrics['time_to_50'])),'median_time_to_25_minutes':float(np.nanmedian(metrics['time_to_25'])),'median_zero_cross_time_minutes':float(np.nanmedian(first_zero)),'median_maximum_widening':float(np.nanmedian(metrics['maximum_widening'])),'median_time_to_maximum_widening_minutes':float(np.nanmedian(metrics['time_to_max_widening'])),'no_convergence_within_60m_rate':float(np.mean(np.isnan(metrics['time_to_50'][valid])))})
    yearly=grouped(events,['pair','year']); loo=[]
    for p,g in events.groupby('pair'):
        for year in range(2019,2024): loo.append({'pair':p,'excluded_year':year,'n':int((g.year!=year).sum()),'mean_change_60m':float(g.loc[g.year!=year,'change_60m'].mean())})
    events['month']=pd.to_datetime(events.event_time,utc=True).dt.to_period('M').astype(str); events['day']=pd.to_datetime(events.event_time,utc=True).dt.date.astype(str)
    concentration={'by_year':grouped(events,['pair','year']),'by_month':grouped(events,['pair','month']),'by_trading_day':grouped(events,['pair','day']),'event_shares':[{'pair':p,'top5_absolute_share':float(g.change_60m.abs().nlargest(5).sum()/g.change_60m.abs().sum()),'top10_absolute_share':float(g.change_60m.abs().nlargest(10).sum()/g.change_60m.abs().sum())} for p,g in events.groupby('pair')]}
    events['volatility_regime']=pd.cut(events.vol,[-np.inf,.3,.7,.9,np.inf],labels=['LOW','NORMAL','HIGH','EXTREME'],right=False)
    wide=pd.DataFrame({p:f.set_index('event_time').z for p,f in method_a.items()}); method_b=[]
    for p in PAIRS:
        residual=rolling_ols_residuals(wide,p); frame=method_a[p][['event_time','session','vol']].copy(); frame['residual']=residual.reindex(pd.DatetimeIndex(frame.event_time)).to_numpy(); frame['abs_residual']=frame.residual.abs(); frame['residual_percentile']=causal_percentile_valid(frame.abs_residual,WINDOW); frame['bucket']=bucket(frame.residual_percentile); frame['year']=pd.to_datetime(frame.event_time,utc=True).dt.year; selected=outcomes(dedup(entry_events(frame))); selected['pair']=p; method_b.append(selected)
    method_b_events=pd.concat(method_b,ignore_index=True)
    if method_b_events.empty: raise RuntimeError('Method B produced no eligible events')
    method_b_summary=summarize(method_b_events)
    old=json.loads((root/'reports/phase21a/residual_convergence.json').read_text()); corrected={r['pair']:r for r in primary if r['horizon_minutes']==60}; comparison=[{'pair':r['pair'],'old_invalid_mean_change_60m':r['mean_change_60m'],'corrected_mean_change_60m':corrected[r['pair']]['mean_absolute_residual_change'],'difference':corrected[r['pair']]['mean_absolute_residual_change']-r['mean_change_60m']} for r in old]
    stable=all(t['survives_fdr'] and t['effect_size']<0 for t in tests) and all(r['mean']<0 for r in yearly) and all(r['mean_change_60m']<0 for r in loo)
    classification='MEAN_REVERSION_PHENOMENON' if stable else 'NO_RELATIVE_VALUE_STRUCTURE'; decision='PHASE_21A_REPRODUCTION_SURVIVED' if stable else 'PHASE_21_FAMILY_CLOSED'
    emit('manifest',{**meta,'datasets':datasets,'code_files':code_files,'method_a_primary':True,'bootstrap_samples':5000,'fdr_alpha':.05})
    emit('event_population',populations); emit('primary_outcomes',primary); emit('path_analysis',path_rows); emit('statistical_inference',tests); emit('yearly_stability',yearly); emit('leave_one_year_out',loo); emit('session_analysis',grouped(events,['pair','session'])); emit('volatility_analysis',grouped(events,['pair','volatility_regime'])); emit('concentration',concentration); emit('method_b_robustness',method_b_summary); emit('old_invalid_vs_corrected_timing',comparison)
    emit('phase21a_reproduction_summary',{'decision':decision,'classification':classification,'runtime_seconds':time.perf_counter()-started,'event_population':populations,'primary_60m':[r for r in primary if r['horizon_minutes']==60],'statistical_inference':tests})
    print(out/'phase21a_reproduction_summary.json')
if __name__=='__main__': main()
