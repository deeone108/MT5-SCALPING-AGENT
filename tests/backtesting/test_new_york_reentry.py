import pandas as pd
import pytest
from mt5_scalping_agent.backtesting.new_york_reentry import NewYorkBollingerReentryConfig, NewYorkBollingerReentryStrategy
from mt5_scalping_agent.domain import TradeDirection

def candles(closes: list[float], final_time: str = "2025-01-06T13:00:00Z") -> pd.DataFrame:
    times=list(pd.date_range(end=final_time,periods=len(closes),freq="min",tz="UTC"))
    return pd.DataFrame({"time":times,"open":closes,"high":[v+0.0002 for v in closes],"low":[v-0.0002 for v in closes],"close":closes,"tick_volume":[1]*len(closes)})

def test_emits_only_one_daily_buy_after_lower_band_reentry() -> None:
    data=candles([1.1010-i*0.00002 for i in range(20)]+[1.0950,1.0975]); strategy=NewYorkBollingerReentryStrategy(); intent=strategy(data)
    assert intent is not None and intent.direction is TradeDirection.BUY
    assert intent.take_profit > float(data.close.iloc[-1]) > intent.stop_loss
    assert strategy(data) is None

def test_ignores_reentry_outside_new_york_session() -> None:
    data=candles([1.1010-i*0.00002 for i in range(20)]+[1.0950,1.0975],"2025-01-06T18:00:00Z")
    assert NewYorkBollingerReentryStrategy()(data) is None

def test_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError,match="must be positive"):
        NewYorkBollingerReentryStrategy(NewYorkBollingerReentryConfig(reward_risk_ratio=0))