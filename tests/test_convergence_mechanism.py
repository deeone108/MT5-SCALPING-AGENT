import numpy as np
import pandas as pd
from mt5_scalping_agent.research.convergence_mechanism import attribute,path_metrics
def test_attribution_and_path_metrics():
 assert attribute(np.array([2.,2.,-2.]),np.array([-.5,0.,.5]),np.array([0.,.5,0.])).tolist()==['TARGET_REVERSAL','COMMON_COMPONENT_CATCH_UP','TARGET_REVERSAL']
 r=np.array([2.,1.4,.8,.4]); times=pd.date_range('2020-01-01',periods=4,freq='5min',tz='UTC'); m=path_metrics(r,times,np.array([0]),15); assert m['time_to_75'][0]==5 and m['time_to_50'][0]==10

def test_path_metrics_reports_missing_exact_path_and_rejects_duplicates():
 times=pd.to_datetime(['2020-01-01T09:00Z','2020-01-01T09:05Z','2020-01-01T09:15Z'])
 result=path_metrics(np.array([2.,1.,.5]),times,np.array([0]),15)
 assert result['status'][0]=='MISSING_EXACT_PATH' and np.isnan(result['time_to_50'][0])
 with np.testing.assert_raises_regex(ValueError,'duplicate'):
  path_metrics(np.array([2.,1.]),pd.to_datetime(['2020-01-01T09:00Z']*2),np.array([0]),5)

def test_maximum_widening_is_clamped_to_zero_at_event_time():
 times=pd.date_range('2020-01-01',periods=4,freq='5min',tz='UTC')
 result=path_metrics(np.array([2.,1.5,1.,.5]),times,np.array([0]),15)
 assert result['maximum_widening'][0]==0 and result['time_to_max_widening'][0]==0

def test_event_timestamp_identity_survives_reset_index():
 import pandas as pd
 full=pd.DataFrame({'event_time':pd.date_range('2020-01-01',periods=100,freq='5min',tz='UTC')})
 event=full.iloc[[20]].copy().reset_index(drop=True)
 assert pd.DatetimeIndex(full.event_time).get_indexer(pd.DatetimeIndex(event.event_time)).tolist()==[20]
