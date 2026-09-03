import pandas as pd
from mt5_scalping_agent.backtesting.online_baselines import NewYorkOpeningRangeRetestStrategy, PreviousDayRangeBreakoutStrategy
from mt5_scalping_agent.domain import TradeDirection

def test_new_york_opening_range_retest_emits_buy_after_rebreak():
    closes=[1.0]*19+[1.05,1.06,1.08,1.055,1.09]
    times=['2025-01-06T11:00:00Z']*19+['2025-01-06T12:00:00Z','2025-01-06T12:29:00Z','2025-01-06T12:31:00Z','2025-01-06T12:32:00Z','2025-01-06T12:33:00Z']
    data=pd.DataFrame({'time':pd.to_datetime(times),'open':closes,'high':[x+.01 for x in closes],'low':[x-.01 for x in closes],'close':closes,'tick_volume':[1]*len(closes)})
    strategy=NewYorkOpeningRangeRetestStrategy()
    for index in range(23): assert strategy(data.iloc[:index+1]) is None
    intent=strategy(data)
    assert intent is not None and intent.direction is TradeDirection.BUY

def test_previous_day_range_breakout_emits_buy():
    closes=[1.0,1.1,1.05,1.2]
    data=pd.DataFrame({'time':pd.to_datetime(['2025-01-06T00:00:00Z','2025-01-06T23:59:00Z','2025-01-07T00:00:00Z','2025-01-07T07:00:00Z']),'open':closes,'high':[1.01,1.11,1.06,1.21],'low':[.99,1.09,1.04,1.19],'close':closes,'tick_volume':[1]*4})
    strategy=PreviousDayRangeBreakoutStrategy()
    for index in range(3): assert strategy(data.iloc[:index+1]) is None
    intent=strategy(data)
    assert intent is not None and intent.direction is TradeDirection.BUY