from pathlib import Path
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_START,DEVELOPMENT_END
from mt5_scalping_agent.research.relative_value_discovery import common_residuals,entry_events,dedup
from mt5_scalping_agent.research.manifest import write_json_atomic
a=LocalResearchArchive(Path('data')); raw={p:a.load_m1(p,DEVELOPMENT_START,DEVELOPMENT_END) for p in ('EURUSD','GBPUSD','USDJPY','USDCAD')}; frames=common_residuals(raw); rows=[]
for p,x in frames.items():
 buckets=x.bucket.value_counts(dropna=False).to_dict(); e=entry_events(x); d=dedup(e)
 rows.append({'pair':p,'raw_m1':len(raw[p]),'aligned_m5':len(x),'valid_z':int(x.z.notna().sum()),'valid_common':int(x.common.notna().sum()),'valid_residual':int(x.residual.notna().sum()),'valid_percentile':int(x.residual_percentile.notna().sum()),'percentile_min':None if x.residual_percentile.dropna().empty else float(x.residual_percentile.min()),'percentile_max':None if x.residual_percentile.dropna().empty else float(x.residual_percentile.max()),'bucket_counts':{str(k):int(v) for k,v in buckets.items()},'entry_events':len(e),'dedup_events':len(d)})
write_json_atomic(Path('reports/phase21a/eligibility_diagnostics.json'),{'status':'INVALID_ZERO_ELIGIBLE_EVENTS','pairs':rows})
print(Path('reports/phase21a/eligibility_diagnostics.json'))