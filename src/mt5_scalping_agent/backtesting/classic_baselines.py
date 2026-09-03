"""Simple public technical-rule baselines for research only."""
from __future__ import annotations
import pandas as pd
from mt5_scalping_agent.backtesting import TradeIntent
from mt5_scalping_agent.domain import TradeDirection

class BollingerMeanReversionStrategy:
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        closes=history['close']; mean=closes.iloc[-20:].mean(); std=closes.iloc[-20:].std(ddof=0); close=float(closes.iloc[-1]);
        if std<=0: return None
        if close < mean-2*std: return TradeIntent(direction=TradeDirection.BUY,stop_loss=close-std,take_profit=mean)
        if close > mean+2*std: return TradeIntent(direction=TradeDirection.SELL,stop_loss=close+std,take_profit=mean)
        return None

class DonchianBreakoutStrategy:
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        prior=history.iloc[-21:-1]; close=float(history['close'].iloc[-1]); high=float(prior['high'].max()); low=float(prior['low'].min()); width=high-low
        if width<=0: return None
        if close>high: return TradeIntent(direction=TradeDirection.BUY,stop_loss=close-width,take_profit=close+2*width)
        if close<low: return TradeIntent(direction=TradeDirection.SELL,stop_loss=close+width,take_profit=close-2*width)
        return None

class MovingAverageCrossoverStrategy:
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        closes=history['close']; fast=closes.iloc[-5:].mean(); slow=closes.iloc[-20:].mean(); price=float(closes.iloc[-1]); prior_fast=closes.iloc[-6:-1].mean(); prior_slow=closes.iloc[-21:-1].mean(); risk=abs(price-slow)
        if risk<=0:return None
        if prior_fast<=prior_slow and fast>slow:return TradeIntent(direction=TradeDirection.BUY,stop_loss=price-risk,take_profit=price+2*risk)
        if prior_fast>=prior_slow and fast<slow:return TradeIntent(direction=TradeDirection.SELL,stop_loss=price+risk,take_profit=price-2*risk)
        return None

class AtrFilterStrategy:
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        prior=history.iloc[-21:-1]; price=float(history.close.iloc[-1]); high=float(prior.high.max()); low=float(prior.low.min()); width=high-low
        if width<=0:return None
        if price>high+0.25*width:return TradeIntent(direction=TradeDirection.BUY,stop_loss=price-width,take_profit=price+2*width)
        if price<low-0.25*width:return TradeIntent(direction=TradeDirection.SELL,stop_loss=price+width,take_profit=price-2*width)
        return None

class NewYorkReversalStrategy(BollingerMeanReversionStrategy):
    """Fixed 20-bar two-standard-deviation reversal during New York UTC hours."""
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        hour=history['time'].iloc[-1].hour
        return super().__call__(history) if 12 <= hour < 17 else None

class NewYorkBollingerRsiReversalStrategy(BollingerMeanReversionStrategy):
    """New York Bollinger reversal requiring RSI(14) exhaustion confirmation."""
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        hour=history['time'].iloc[-1].hour
        if not 12 <= hour < 17: return None
        closes=history['close']; changes=closes.diff().iloc[-14:]; gains=changes.clip(lower=0).mean(); losses=-changes.clip(upper=0).mean()
        rsi=100.0 if losses == 0 else (0.0 if gains == 0 else 100.0 - 100.0/(1.0+gains/losses))
        intent=super().__call__(history)
        if intent is None: return None
        if intent.direction is TradeDirection.BUY and rsi <= 30: return intent
        if intent.direction is TradeDirection.SELL and rsi >= 70: return intent
        return None
class DoubleBollingerBreakoutStrategy:
    """Continuation after a 20-bar outer Bollinger-band break."""
    uses_latest_candle_only=True; required_history_bars=21
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        closes=history['close']; mean=closes.iloc[-20:].mean(); std=closes.iloc[-20:].std(ddof=0); close=float(closes.iloc[-1])
        if std <= 0: return None
        if close > mean+2*std:
            risk=close-(mean+std); return TradeIntent(direction=TradeDirection.BUY,stop_loss=mean+std,take_profit=close+2*risk)
        if close < mean-2*std:
            risk=(mean-std)-close; return TradeIntent(direction=TradeDirection.SELL,stop_loss=mean-std,take_profit=close-2*risk)
        return None

class RsiTrendBreakoutStrategy:
    """20-bar channel break with RSI(14) momentum and 20-bar trend alignment."""
    uses_latest_candle_only=True; required_history_bars=22
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        closes=history['close']; current=float(closes.iloc[-1]); prior=history.iloc[-21:-1]; changes=closes.diff().iloc[-14:]; gains=changes.clip(lower=0).mean(); losses=-changes.clip(upper=0).mean()
        rsi=100.0 if losses == 0 else (0.0 if gains == 0 else 100.0-100.0/(1.0+gains/losses)); slow=float(closes.iloc[-21:-1].mean()); high=float(prior['high'].max()); low=float(prior['low'].min())
        if current > high and current > slow and rsi >= 55:
            risk=current-low; return TradeIntent(direction=TradeDirection.BUY,stop_loss=low,take_profit=current+2*risk)
        if current < low and current < slow and rsi <= 45:
            risk=high-current; return TradeIntent(direction=TradeDirection.SELL,stop_loss=high,take_profit=current-2*risk)
        return None

class AtrFilteredMeanReversionStrategy(BollingerMeanReversionStrategy):
    """Bollinger mean reversion only when ATR(14) is no more than twice recent median volatility."""
    uses_latest_candle_only=True; required_history_bars=22
    def __call__(self, history: pd.DataFrame) -> TradeIntent|None:
        highs,lows,closes=history['high'],history['low'],history['close']; previous=closes.shift(1); true_range=pd.concat([highs-lows,(highs-previous).abs(),(lows-previous).abs()],axis=1).max(axis=1)
        atr=float(true_range.iloc[-14:].mean()); baseline=float(true_range.iloc[-21:-1].median())
        if atr <= 0 or baseline <= 0 or atr > 2.0*baseline: return None
        return super().__call__(history)