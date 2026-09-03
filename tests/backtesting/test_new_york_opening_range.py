import pandas as pd
from mt5_scalping_agent.backtesting.new_york_opening_range import NewYorkOpeningRangeBreakoutStrategy
from mt5_scalping_agent.domain import TradeDirection

def test_emits_one_trend_aligned_buy_after_new_york_opening_range_break() -> None:
 closes=[1.0]*19+[1.05,1.06,1.08]
 data=pd.DataFrame({'time':pd.to_datetime(['2025-01-06T11:58:00Z']*19+['2025-01-06T12:00:00Z','2025-01-06T12:59:00Z','2025-01-06T13:00:00Z']),'open':closes,'high':[x+.01 for x in closes],'low':[x-.01 for x in closes],'close':closes,'tick_volume':[1]*len(closes)})
 strategy=NewYorkOpeningRangeBreakoutStrategy()
 for index in range(21): assert strategy(data.iloc[:index+1]) is None
 intent=strategy(data)
 assert intent is not None
 assert intent.direction is TradeDirection.BUY
 assert strategy(data) is None