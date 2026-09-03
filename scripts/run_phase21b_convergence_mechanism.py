"""Run Phase 21B mechanism attribution; no strategy or execution."""
from pathlib import Path
import json
import numpy as np`nimport pandas as pd
def nullable(value):
    value=float(value)
    return value if np.isfinite(value) else None
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.relative_value_discovery import common_residuals,entry_events,dedup
from mt5_scalping_agent.research.convergence_mechanism import attribute,path_metrics
from mt5_scalping_agent.research.manifest import write_json_atomic
PAIRS=('EURUSD','GBPUSD','USDJPY','USDCAD')
def main():
 a=LocalResearchArchive(Path('data')); raw={p:a.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in PAIRS}; frames=common_residuals(raw); rows=[]
 for p,f in frames.items():
  e=dedup(entry_events(f)); full=f.reset_index(drop=True); lookup=pd.DatetimeIndex(full.event_time); pos=lookup.get_indexer(pd.DatetimeIndex(e.event_time)); valid=(pos>=0)&(pos+60<len(full)); e=e.loc[valid].copy(); pos=pos[valid]; target=full.z.to_numpy(); common=full.common.to_numpy(); initial=full.residual.to_numpy()[pos]; tc=target[pos+60]-target[pos]; cc=common[pos+60]-common[pos]; labels=attribute(initial,tc,cc); paths=path_metrics(full.residual.to_numpy(),pos); rows.append({'pair':p,'events':len(e),'mechanism_proportions':{k:float((labels==k).mean()) for k in ('TARGET_REVERSAL','COMMON_COMPONENT_CATCH_UP','BOTH','AMBIGUOUS')},'median_target_change_z':nullable(np.median(tc)),'median_common_change_z':nullable(np.median(cc)),'median_time_to_75':nullable(np.nanmedian(paths['time_to_75'])),'median_time_to_50':nullable(np.nanmedian(paths['time_to_50'])),'median_time_to_25':nullable(np.nanmedian(paths['time_to_25'])),'median_max_widening_z':nullable(np.median(paths['maximum_widening']))})
 out=Path('reports/phase21b'); out.mkdir(parents=True,exist_ok=True); write_json_atomic(out/'mechanism_attribution.json',rows); write_json_atomic(out/'phase21b_summary.json',{'status':'INCOMPLETE_EVIDENCE','event_population':rows,'stop':'Mechanism attribution calculated; remaining stability, pairwise, cost, and FDR work is required before a Phase 21B classification.'}); print(out/'phase21b_summary.json')
if __name__=='__main__':main()