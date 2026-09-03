"""Run Phase 20A path and liquidity behaviour discovery; descriptive only."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START, DEVELOPMENT_END
from mt5_scalping_agent.research.intraday_path_discovery import build_observations,deduplicate_observations,path_quality_table,block_bootstrap_difference,fdr_tests,ocr_quality,leave_one_year_out
from mt5_scalping_agent.research.manifest import local_archive_dataset, write_json_atomic

PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD')
def records(frame,by,columns):
    result=frame.groupby(by,dropna=False)[columns].agg(['count','mean','median']).reset_index()
    result.columns=[str(a) if not b else f'{a}_{b}' for a,b in result.columns.to_flat_index()]
    return result.to_dict(orient='records')
def main():
    root=Path('.').resolve(); archive=LocalResearchArchive(root/'data'); costs=json.loads((root/'reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json').read_text())['models']; frozen={p:{'base':float(costs[p]['base']['round_trip_cost_pips']),'stress':float(costs[p]['stress']['round_trip_cost_pips'])} for p in PAIRS}; primary=[]; attrition=[]; quality=[]
    for pair in PAIRS:
        m1=archive.load_m1(pair,DEVELOPMENT_START,DEVELOPMENT_END); events=build_observations(pair,m1); dedup=deduplicate_observations(events); primary.append(dedup); attrition.append({'pair':pair,'raw_observations':len(events),'eligible_observations':len(events),'deduplicated_events':len(dedup),'suppressed_percent':float(100*(1-len(dedup)/len(events)))}); quality.append({'pair':pair,'m1_rows':len(m1),'first_timestamp':m1.time.iloc[0].isoformat(),'last_timestamp':m1.time.iloc[-1].isoformat()})
    events=pd.concat(primary,ignore_index=True); tests=[]
    for pair,group in events.groupby('pair'):
        for state in ('vol_15m_bucket','per_15m_bucket','vol_15m_change_bucket'):
            valid=group[state].notna(); top=group[state].astype(str).str.startswith('95-') if state=='per_15m_bucket' else group[state].astype(str).str.startswith(('95-','99-'))
            result=block_bootstrap_difference(group.loc[valid],'continuation_60m_pips',top.loc[valid]); result.update({'pair':pair,'family':state,'comparison':'highest_fixed_bucket_vs_other','outcome':'continuation_60m_pips'}); tests.append(result)
    tests=fdr_tests(tests)
    reports={'manifest':{'phase':'20A','evidence_status':'DEVELOPMENT_DESCRIPTIVE_RESEARCH','period':{'start':DEVELOPMENT_START.isoformat(),'end_exclusive':DEVELOPMENT_END.isoformat()},'pairs':list(PAIRS),'post_2023_accessed':False,'mt5_accessed':False,'strategy_created':False,'datasets':{pair:local_archive_dataset(archive_root=root/'data',archive=archive,symbol=pair,periods=[(DEVELOPMENT_START,DEVELOPMENT_END)],project_root=root) for pair in PAIRS},'random_seed':20020,'bootstrap_samples':5000},'data_quality':quality,'path_efficiency':path_quality_table(events,'per_15m_bucket'),'volatility_expansion':path_quality_table(events,'vol_15m_bucket'),'volatility_change':path_quality_table(events,'vol_15m_change_bucket'),'liquidity_transitions':records(events[events.transition!='none'],['pair','transition'],['forward_60m_signed','forward_60m_per','forward_60m_mfe','forward_60m_mae']),'movement_quality':records(events,['pair','session'],['forward_60m_absolute','forward_60m_per','forward_60m_mfe','forward_60m_mae','forward_60m_reversals']),'opportunity_vs_path_quality':ocr_quality(events,frozen),'session_analysis':records(events,['pair','session'],['continuation_60m_pips','forward_60m_per','forward_60m_mfe','forward_60m_mae']),'pair_stability':records(events,['pair'],['continuation_60m_pips','forward_60m_per','forward_60m_mfe','forward_60m_mae']),'yearly_stability':records(events.assign(year=pd.to_datetime(events.event_time,utc=True).dt.year),['pair','year'],['continuation_60m_pips','forward_60m_per','forward_60m_mfe','forward_60m_mae']),'concentration':{'event_attrition':attrition,'leave_one_year_out':{pair:leave_one_year_out(group,'continuation_60m_pips') for pair,group in events.groupby('pair')}},'explanatory_models':{'scope':'descriptive nested-model placeholder; no model selection or trading predictions','outcomes':['continuation_60m_pips','forward_60m_per'],'covariates':['session','year','pre_15m_signed_pips','vol_15m_percentile','per_15m_percentile','vol_15m_change_percentile']},'statistical_tests':tests}
    out=root/'reports/phase20a'; out.mkdir(parents=True,exist_ok=True)
    for name,value in reports.items(): write_json_atomic(out/f'{name}.json',value)
    survived=[x for x in tests if x['survives_fdr'] and abs(x['mean_difference'])>=frozen[x['pair']]['stress']]
    classification='PATH_STRUCTURE_ONLY' if survived else 'MOVEMENT_WITHOUT_PREDICTABILITY'
    summary={'classification':classification,'evidence_status':'DEVELOPMENT_DESCRIPTIVE_RESEARCH','event_attrition':attrition,'fdr_surviving_economically_material_tests':survived,'all_tests':tests,'stop':'Phase 20A complete. No strategy, registry candidate, MT5 access, or further phase is created.'}
    write_json_atomic(out/'phase20a_summary.json',summary); print(f'Report: {out/"phase20a_summary.json"}')
if __name__=='__main__': main()