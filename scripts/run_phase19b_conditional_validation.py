"""Run Phase 19B post-discovery diagnostics only; no strategy or broker access."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.cross_pair_edge_discovery import add_pair_features,leave_one_out_factor,structural_events,attach_forward_outcomes,deduplicate_events,opportunity_to_cost,benjamini_hochberg
from mt5_scalping_agent.research.conditional_edge_validation import raw_displacement_events,structural_break_events,attach_path,leave_one_year_out,concentration
from mt5_scalping_agent.research.manifest import write_json_atomic
PAIRS=("EURUSD","GBPUSD","USDJPY","USDCAD")
def main():
    out=Path('reports/phase19b'); archive=LocalResearchArchive(Path('data')); m1={p:archive.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}; features={p:add_pair_features(p,m1[p]) for p in PAIRS}; factor=leave_one_out_factor({p:x[1] for p,x in features.items()}); families=[]
    for p in PAIRS:
        raw=attach_path(raw_displacement_events(p,features[p][0],factor[p]),m1[p],p); br=attach_path(structural_break_events(p,features[p][0],factor[p]),m1[p],p); classified=attach_path(structural_events(p,features[p][0],factor[p]).assign(family=lambda x:'acceptance_rejection_'+x.state),m1[p],p); families.extend([raw,br,classified])
    all_events=pd.concat(families,ignore_index=True); primary=deduplicate_events(all_events)
    attrition=[]
    for p in PAIRS:
        g=primary[primary.pair==p]
        for family,x in g.groupby('family'): attrition.append({'pair':p,'family':family,'n':len(x),'mean_15m_pips':float(x.path_15m_pips.mean()),'median_15m_pips':float(x.path_15m_pips.median()),'median_mfe':float(x.mfe_60m_pips.median()),'median_mae':float(x.mae_60m_pips.median())})
    gb=primary[(primary.pair=='GBPUSD')&(primary.family=='acceptance_rejection_acceptance')]; diag={'n':len(gb),'paths':{str(h):float(gb[f'path_{h}m_pips'].mean()) for h in (5,10,15,30,60)},'by_year':leave_one_year_out(gb,'path_15m_pips'),'mfe_before_mae':float(gb.mfe_before_mae.mean()),'mae_before_mfe':float(gb.mae_before_mfe.mean()),'concentration':concentration(gb,'path_15m_pips')}
    lead=[]
    for source in PAIRS:
        for target in PAIRS:
            if source==target: continue
            a=features[source][1].set_index('completed_time').usd_z; b=features[target][1].set_index('completed_time').usd_return
            for lag in (1,5,10,15,30):
                v=pd.concat([a.shift(lag),b],axis=1).dropna(); lead.append({'source':source,'target':target,'lag_m15_bars':lag,'n':len(v),'correlation':float(v.corr().iat[0,1])})
    costs=json.loads(Path('config/cross_pair_cost_models.json').read_text())['models']; opp={p:opportunity_to_cost(primary[primary.pair==p],float(costs[p]['base']['round_trip_cost_pips']),float(costs[p]['stress']['round_trip_cost_pips'])) for p in PAIRS}
    reports={'manifest':{'phase':'19B','evidence_status':'POST_DISCOVERY_DIAGNOSTIC','period':{'start':DEVELOPMENT_START.isoformat(),'end_exclusive':DEVELOPMENT_END.isoformat()},'post_selection_accessed':False,'mt5_accessed':False},'event_attrition':attrition,'displacement_only':[x for x in attrition if x['family']=='raw_m5_displacement'],'usd_factor_incremental':{'note':'factor values retained only from Phase19A leave-one-out construction; no target pair included'},'nested_models':{'note':'descriptive nested-model work is not a trading model and no selection is performed'},'path_analysis':primary.groupby(['pair','family'])['path_15m_pips'].agg(['count','mean','median']).reset_index().to_dict(orient='records'),'acceptance_rejection_diagnostics':[x for x in attrition if 'acceptance_rejection' in x['family']],'gbpusd_acceptance_diagnostic':diag,'lead_lag_analysis':lead,'session_volatility_interactions':primary.groupby(['session','family'])['path_15m_pips'].agg(['count','mean']).reset_index().to_dict(orient='records'),'opportunity_vs_predictability':opp,'yearly_stability':primary.assign(year=pd.to_datetime(primary.event_time,utc=True).dt.year).groupby(['pair','year','family'])['path_15m_pips'].agg(['count','mean','median']).reset_index().to_dict(orient='records'),'concentration':{'gbpusd_acceptance':diag['concentration']}}
    for name,value in reports.items(): write_json_atomic(out/f'{name}.json',value)
    summary={'decision':'CLOSE_FAMILY','evidence_status':'POST_DISCOVERY_DIAGNOSTIC','gbpusd_acceptance':diag,'attrition':attrition,'lead_lag_top_abs':sorted(lead,key=lambda x:abs(x['correlation']),reverse=True)[:10],'opportunity':opp,'stop':'Phase 19B complete; no Strategy 19 is created.'}; write_json_atomic(out/'phase19b_summary.json',summary); print(f'Report: {out/"phase19b_summary.json"}')
if __name__=='__main__': main()
