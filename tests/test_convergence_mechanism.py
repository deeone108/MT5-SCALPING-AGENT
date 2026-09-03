import numpy as np
from mt5_scalping_agent.research.convergence_mechanism import attribute,path_metrics
def test_attribution_and_path_metrics():
 assert attribute(np.array([2.,2.,-2.]),np.array([-.5,0.,.5]),np.array([0.,.5,0.])).tolist()==['TARGET_REVERSAL','COMMON_COMPONENT_CATCH_UP','TARGET_REVERSAL']
 r=np.array([2.,1.4,.8,.4]); m=path_metrics(r,np.array([0]),3); assert m['time_to_75'][0]==1 and m['time_to_50'][0]==2

def test_event_timestamp_identity_survives_reset_index():
 import pandas as pd
 full=pd.DataFrame({'event_time':pd.date_range('2020-01-01',periods=100,freq='5min',tz='UTC')})
 event=full.iloc[[20]].copy().reset_index(drop=True)
 assert pd.DatetimeIndex(full.event_time).get_indexer(pd.DatetimeIndex(event.event_time)).tolist()==[20]
