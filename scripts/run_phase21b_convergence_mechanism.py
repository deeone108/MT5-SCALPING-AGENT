"""Run Phase 21B mechanism attribution; no strategy or execution."""
from pathlib import Path
import numpy as np
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.relative_value_discovery import common_residuals,entry_events,dedup
from mt5_scalping_agent.research.convergence_mechanism import attribute,path_metrics
from mt5_scalping_agent.research.manifest import write_json_atomic

PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD')
def nullable(value):
    value=float(value); return value if np.isfinite(value) else None

def main():
    archive=LocalResearchArchive(Path('data'))
    raw={p:archive.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}
    rows=[]
    for pair,frame in common_residuals(raw).items():
        events=dedup(entry_events(frame)); full=frame.reset_index(drop=True)
        timeline=pd.DatetimeIndex(full.event_time)
        positions=timeline.get_indexer(pd.DatetimeIndex(events.event_time))
        endpoints=timeline.get_indexer(pd.DatetimeIndex(events.event_time)+pd.Timedelta(minutes=60))
        valid=(positions>=0)&(endpoints>=0)
        events=events.loc[valid].copy(); positions=positions[valid]; endpoints=endpoints[valid]
        target=full.z.to_numpy(); common=full.common.to_numpy()
        target_change=target[endpoints]-target[positions]; common_change=common[endpoints]-common[positions]
        labels=attribute(full.residual.to_numpy()[positions],target_change,common_change)
        paths=path_metrics(full.residual.to_numpy(),full.event_time,positions)
        complete=paths['valid']; labels=labels[complete]; target_change=target_change[complete]; common_change=common_change[complete]
        rows.append({'pair':pair,'events':int(complete.sum()),'mechanism_proportions':{k:float((labels==k).mean()) for k in ('TARGET_REVERSAL','COMMON_COMPONENT_CATCH_UP','BOTH','AMBIGUOUS')},'median_target_change_z':nullable(np.median(target_change)),'median_common_change_z':nullable(np.median(common_change)),'median_time_to_75':nullable(np.nanmedian(paths['time_to_75'][complete])),'median_time_to_50':nullable(np.nanmedian(paths['time_to_50'][complete])),'median_time_to_25':nullable(np.nanmedian(paths['time_to_25'][complete])),'median_max_widening_z':nullable(np.median(paths['maximum_widening'][complete]))})
    out=Path('reports/phase21b'); out.mkdir(parents=True,exist_ok=True)
    write_json_atomic(out/'mechanism_attribution.json',rows)
    write_json_atomic(out/'phase21b_summary.json',{'status':'INCOMPLETE_EVIDENCE','event_population':rows,'stop':'Mechanism attribution calculated; remaining work is required.'})
if __name__=='__main__': main()
