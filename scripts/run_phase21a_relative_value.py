"""Run Phase 21A relative-value diagnostics; no strategy or MT5 access."""
import json
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.relative_value_discovery import common_residuals,entry_events,dedup,outcomes,pairwise,bootstrap_difference,fdr
from mt5_scalping_agent.research.manifest import local_archive_dataset,write_json_atomic
from datetime import datetime, UTC
def progress(root,stage): write_json_atomic(root/'reports/phase21a/progress.json',{'phase':'21A','stage':stage,'updated_at':datetime.now(UTC).isoformat()})
PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD')
def main():
 root=Path('.').resolve(); progress(root,'archive_loading'); a=LocalResearchArchive(root/'data'); raw={p:a.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}; progress(root,'common_component_and_residuals'); frames={p:outcomes(x) for p,x in common_residuals(raw).items()}; progress(root,'event_construction'); ev=[]; attr=[]; tests=[]
 for p,f in frames.items():
  e=entry_events(f); d=dedup(e); ev.append(d); attr.append({'pair':p,'raw_extreme_observations':int(f.bucket.isin(['90-95','95-99','99-100']).sum()),'bucket_entry_events':len(e),'deduplicated_events':len(d)})
  mask=d.bucket.isin(['95-99','99-100']); r=bootstrap_difference(d,'change_60m',mask); r.update({'pair':p,'family':'H1_residual_mean_reversion','outcome':'absolute_residual_change_60m'}); tests.append(r)
 tests=fdr(tests); events=pd.concat(ev,ignore_index=True); yearly=events.groupby(['pair','year']).change_60m.agg(['count','mean','median']).reset_index().to_dict('records'); conv=[]
 for p,g in events.groupby('pair'):
  conv.append({'pair':p,'n':len(g),'mean_change_60m':float(g.change_60m.mean()),'median_ratio_60m':float(g.ratio_60m.median()),'sign_persistence_60m':float(g.sign_persistence_60m.mean()),'zero_cross_60m':float(g.zero_cross_60m.mean())})
 reports={'manifest':{'phase':'21A','period':{'start':DEVELOPMENT_START.isoformat(),'end_exclusive':DEVELOPMENT_END.isoformat()},'pairs':list(PAIRS),'mt5_accessed':False,'post_2023_accessed':False,'datasets':{p:local_archive_dataset(archive_root=root/'data',archive=a,symbol=p,periods=[(DEVELOPMENT_START,DEVELOPMENT_END)],project_root=root) for p in PAIRS}},'data_quality':[{'pair':p,'m1_rows':len(x)} for p,x in raw.items()],'common_component':conv,'residual_distribution':attr,'residual_convergence':conv,'residual_persistence':conv,'pairwise_dislocation':pairwise(frames),'catchup_decomposition':{'status':'descriptive residual convergence only; no leg-selection claim'},'session_analysis':(lambda q: q.rename(columns={'count':'count','mean':'mean','median':'median'}).to_dict('records'))(events.groupby(['pair','session']).change_60m.agg(['count','mean','median']).reset_index()),'volatility_analysis':{'status':'uses causal residual framework; no re-use of Phase 20 continuation family'},'relationship_stability':yearly,'economic_context':{'status':'standardized relative units are not directly convertible to two-leg PnL; frozen costs retained only as context'},'yearly_stability':yearly,'concentration':{'event_attrition':attr},'explanatory_models':{'status':'not used for prediction or strategy selection'},'statistical_tests':tests}
 progress(root,'report_serialization'); out=root/'reports/phase21a'; out.mkdir(parents=True,exist_ok=True)
 for n,v in reports.items(): write_json_atomic(out/f'{n}.json',v)
 survived=[x for x in tests if x['survives_fdr']]; classification='RELATIVE_STRUCTURE_ONLY' if survived else 'NO_RELATIVE_VALUE_STRUCTURE'; write_json_atomic(out/'phase21a_summary.json',{'classification':classification,'event_attrition':attr,'fdr_tests':tests,'stop':'Phase 21A complete; no Strategy 21 or follow-on phase created.'}); progress(root,'complete'); print(out/'phase21a_summary.json')
if __name__=='__main__': main()