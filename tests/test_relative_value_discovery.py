import pandas as pd
import numpy as np
import pytest
from mt5_scalping_agent.research.relative_value_discovery import require_development, standardize_prior, entry_events, dedup, outcomes

def test_boundary_standardization_entries_dedup_and_outcomes():
 with pytest.raises(ValueError): require_development(pd.DataFrame({'time':pd.to_datetime(['2024-01-01T00:00Z'])}))
 x=pd.Series([1.,2.,3.,4.]); assert pd.isna(standardize_prior(x,2).iloc[1])
 f=pd.DataFrame({'event_time':pd.date_range('2020-01-01',periods=4,freq='30min',tz='UTC'),'bucket':['80-90','90-95','95-99','80-90'],'residual':[2.,1.,-.5,.2]})
 assert len(entry_events(f))==1; assert len(dedup(f))==2
 result=outcomes(f,(30,)); assert result['change_30m'].iloc[0]==pytest.approx(-1.0); assert result['outcome_30m_status'].iloc[0]=='AVAILABLE'

def test_outcomes_require_exact_endpoint_and_reject_duplicates():
 f=pd.DataFrame({'event_time':pd.to_datetime(['2020-01-01T09:00Z','2020-01-01T09:05Z','2020-01-01T09:10Z','2020-01-01T09:20Z']),'residual':[2.,1.5,1.,.5]})
 result=outcomes(f,(5,15)); assert result['change_5m'].iloc[0]==pytest.approx(-.5); assert pd.isna(result['change_15m'].iloc[0]); assert result['outcome_15m_status'].iloc[0]=='MISSING_EXACT_ENDPOINT'
 duplicate=pd.concat([f,f.iloc[[0]]],ignore_index=True)
 with pytest.raises(ValueError,match='duplicate'): outcomes(duplicate,(5,))

def test_all_frozen_horizons_resolve_by_elapsed_timestamp_after_reset_index():
 times=pd.date_range('2020-01-01T09:00Z',periods=13,freq='5min')
 frame=pd.DataFrame({'event_time':times,'residual':np.arange(13,dtype=float)}).iloc[:].reset_index(drop=True)
 result=outcomes(frame)
 for horizon in (5,10,15,30,60):
  assert result[f'change_{horizon}m'].iloc[0]==pytest.approx(horizon/5)
  assert result[f'outcome_{horizon}m_status'].iloc[0]=='AVAILABLE'

def test_fractional_percentile_buckets_match_frozen_percentage_boundaries():
 from mt5_scalping_agent.research.relative_value_discovery import bucket
 values=pd.Series([0.0,.499999,.5,.699999,.7,.899999,.9,.949999,.95,.989999,.99,1.0])
 assert bucket(values).tolist()==['0-50','0-50','50-70','50-70','70-80','80-90','90-95','90-95','95-99','95-99','99-100','99-100']
