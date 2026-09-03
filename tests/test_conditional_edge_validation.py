import numpy as np
import pandas as pd
import pytest
from mt5_scalping_agent.research.conditional_edge_validation import attach_path, lead_lag, leave_one_year_out

def test_paths_are_direction_adjusted_and_use_future_only_as_outcomes():
    times = pd.date_range("2019-01-01", periods=100, freq="min", tz="UTC")
    close=1+np.arange(100)*.0001
    m1=pd.DataFrame({"time":times,"open":close,"high":close+.0001,"low":close-.0001,"close":close,"tick_volume":1})
    events = pd.DataFrame({"pair":["EURUSD"], "event_time":[times[10]], "direction":[1], "family":["raw"]})
    output = attach_path(events, m1, "EURUSD")
    assert output.path_5m_pips.iat[0] == pytest.approx(5)
    assert output.time_to_mfe_minutes.iat[0] == 60
    assert output.mae_before_mfe.iat[0]

def test_lag_and_leave_year_out_are_causal():
    values = pd.Series([1., 2., 3.])
    assert pd.isna(lead_lag(values, 1).iat[0])
    events = pd.DataFrame({"event_time":pd.to_datetime(["2019-01-01","2020-01-01"], utc=True), "x":[1.,3.]})
    assert leave_one_year_out(events, "x")[0]["mean"] == 3.
