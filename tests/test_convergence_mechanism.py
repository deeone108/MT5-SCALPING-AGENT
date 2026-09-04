import numpy as np
import pytest
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

def test_phase21b_contributions_labels_and_zero_cross_remainder():
 from mt5_scalping_agent.research.convergence_mechanism import contribution_arithmetic,mechanism_labels
 d,t,c,r=contribution_arithmetic(np.array([2.,2.,2.]),np.array([1.,1.,-1.]),np.array([-.5,0.,-3.]),np.array([0.,.5,0.]))
 assert np.allclose(d,t+c+r)
 assert mechanism_labels(d,t,c).tolist()==['TARGET_REVERSAL','COMMON_CATCH_UP','TARGET_REVERSAL']
 assert r[2] == -2.

def test_phase21b_adverse_path_stops_before_first_half_convergence():
 from mt5_scalping_agent.research.convergence_mechanism import adverse_path_metrics
 x=adverse_path_metrics(np.array([2.]),np.array([[2.5,3.,.9,4.]]),np.array([5,10,15,20]))
 assert x['max_pre_convergence_widening'][0]==1. and x['time_to_worst_widening'][0]==10

def test_phase21b_target_excursions_are_directional_native_pips():
 from mt5_scalping_agent.research.convergence_mechanism import target_excursions
 x=target_excursions(np.array([1.]),np.array([[1.001,0.999]]),np.array([1.]),.0001,np.array([5,10]))
 assert x['mfe'][0]==pytest.approx(10) and x['mae'][0]==pytest.approx(-10)