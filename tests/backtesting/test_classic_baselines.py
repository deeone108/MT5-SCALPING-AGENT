import pandas as pd
from mt5_scalping_agent.backtesting.classic_baselines import AtrFilteredMeanReversionStrategy, BollingerMeanReversionStrategy, DonchianBreakoutStrategy, DoubleBollingerBreakoutStrategy, NewYorkBollingerRsiReversalStrategy, RsiTrendBreakoutStrategy
from mt5_scalping_agent.domain import TradeDirection

def frame(close):
 return pd.DataFrame({'time':pd.date_range('2025-01-01',periods=len(close),freq='min',tz='UTC'),'open':close,'high':[x+.01 for x in close],'low':[x-.01 for x in close],'close':close,'tick_volume':[1]*len(close)})
def test_bollinger_and_donchian_baselines_emit_intents():
 b=BollingerMeanReversionStrategy(); d=DonchianBreakoutStrategy();
 assert b(frame([1.0]*20+[.8])).direction is TradeDirection.BUY
 assert d(frame([1.0]*20+[1.2])).direction is TradeDirection.BUY

def test_new_york_bollinger_rsi_reversal_requires_session_and_exhaustion():
 bearish=[1.2-index*.005 for index in range(20)]+[.8]; data=frame(bearish); data.loc[:,'time']=pd.date_range('2025-01-01 12:00',periods=len(data),freq='min',tz='UTC')
 assert NewYorkBollingerRsiReversalStrategy()(data).direction is TradeDirection.BUY
 data.loc[:,'time']=pd.date_range('2025-01-01 11:00',periods=len(data),freq='min',tz='UTC')
 assert NewYorkBollingerRsiReversalStrategy()(data) is None
def test_double_bollinger_and_atr_filtered_reversion_emit_buy_intents():
    double=DoubleBollingerBreakoutStrategy(); atr=AtrFilteredMeanReversionStrategy()
    assert double(frame([1.0]*20+[1.2])).direction is TradeDirection.BUY
    assert atr(frame([1.0]*20+[.8])).direction is TradeDirection.BUY

def test_rsi_trend_breakout_emits_a_buy_intent():
    strategy=RsiTrendBreakoutStrategy()
    assert strategy(frame([1.0]*21+[1.2])).direction is TradeDirection.BUY