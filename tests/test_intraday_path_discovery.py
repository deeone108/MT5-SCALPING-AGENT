from datetime import UTC
import numpy as np
import pandas as pd
import pytest
from mt5_scalping_agent.research.intraday_path_discovery import _window_metrics, build_observations, deduplicate_observations, require_development_only, transition_label, block_bootstrap_difference, fdr_tests

def test_path_metrics_include_efficiency_excursions_and_runs():
    prices=np.array([1.,1.1,1.2,1.1,1.3,1.4,1.2]); returns=np.diff(prices,prepend=prices[0]); positions=np.array([3]); pre=_window_metrics(prices,returns,positions,3,.1,forward=False); future=_window_metrics(prices,returns,positions,3,.1,forward=True,direction=np.array([1.]))
    assert pre['signed'][0] == pytest.approx(1.0); assert pre['per'][0] == pytest.approx(1/3); assert pre['reversals'][0] == 1; assert pre['run_length'][0] == 2
    assert future['mfe'][0] == pytest.approx(3.0); assert future['mae'][0] == pytest.approx(1.0); assert future['time_to_mfe'][0] == 2; assert future['mfe_before_mae'][0]

def test_zero_path_is_missing_and_future_cannot_change_causal_features():
    times=pd.date_range('2020-01-01',periods=180,freq='min',tz='UTC'); prices=np.ones(180); prices[:100]+=np.arange(100)*.0001; frame=pd.DataFrame({'time':times,'open':prices,'high':prices,'low':prices,'close':prices,'tick_volume':1})
    base=build_observations('EURUSD',frame); altered=frame.copy(); altered.loc[120:,['open','high','low','close']]+=1; later=build_observations('EURUSD',altered)
    assert base.loc[base.event_time<times[100],'pre_15m_per'].equals(later.loc[later.event_time<times[100],'pre_15m_per'])
    assert base['pre_5m_per'].dropna().between(0,1).all()

def test_dedup_transition_boundary_bootstrap_and_fdr_are_deterministic():
    times=pd.to_datetime(['2020-06-01 07:00Z','2020-06-01 07:30Z','2020-06-01 08:00Z','2020-06-02 08:00Z']); events=pd.DataFrame({'pair':['EURUSD']*4,'event_time':times,'value':[1.,2.,3.,4.],'state':['a','a','b','b']})
    assert len(deduplicate_observations(events)) == 3
    labels=transition_label(pd.Series(times)); assert labels.iloc[0] == 'london_open'
    first=block_bootstrap_difference(events,'value',events.state.eq('b'),samples=20,seed=7); second=block_bootstrap_difference(events,'value',events.state.eq('b'),samples=20,seed=7); assert first==second
    assert all('q_value' in row for row in fdr_tests([{'p_value':.01},{'p_value':.4}]))

def test_2024_is_refused():
    frame=pd.DataFrame({'time':pd.to_datetime(['2024-01-01T00:00:00Z'])})
    with pytest.raises(ValueError,match='2024'): require_development_only(frame)

def test_build_observations_rejects_missing_and_duplicate_m1():
 times=pd.date_range('2020-01-01',periods=180,freq='min',tz='UTC'); price=np.ones(180); frame=pd.DataFrame({'time':times,'open':price,'high':price,'low':price,'close':price,'tick_volume':1})
 with pytest.raises(ValueError,match='consecutive'): build_observations('EURUSD',frame.drop(index=10).reset_index(drop=True))
 duplicate=frame.copy(); duplicate.loc[10,'time']=duplicate.loc[9,'time']
 with pytest.raises(ValueError,match='duplicate'): build_observations('EURUSD',duplicate)
