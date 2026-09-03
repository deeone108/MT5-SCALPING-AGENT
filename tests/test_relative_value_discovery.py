import pandas as pd
import numpy as np
import pytest
from mt5_scalping_agent.research.relative_value_discovery import require_development, standardize_prior, entry_events, dedup, outcomes

def test_boundary_standardization_entries_dedup_and_outcomes():
 with pytest.raises(ValueError): require_development(pd.DataFrame({'time':pd.to_datetime(['2024-01-01T00:00Z'])}))
 x=pd.Series([1.,2.,3.,4.]); assert pd.isna(standardize_prior(x,2).iloc[1])
 f=pd.DataFrame({'event_time':pd.date_range('2020-01-01',periods=4,freq='30min',tz='UTC'),'bucket':['80-90','90-95','95-99','80-90'],'residual':[2.,1.,-.5,.2]})
 assert len(entry_events(f))==1; assert len(dedup(f))==2; assert outcomes(f,(1,))['change_1m'].iloc[0]==pytest.approx(-1.0)

def test_fractional_percentile_buckets_match_frozen_percentage_boundaries():
 from mt5_scalping_agent.research.relative_value_discovery import bucket
 values=pd.Series([0.0,.499999,.5,.699999,.7,.899999,.9,.949999,.95,.989999,.99,1.0])
 assert bucket(values).tolist()==['0-50','0-50','50-70','50-70','70-80','80-90','90-95','90-95','95-99','95-99','99-100','99-100']
