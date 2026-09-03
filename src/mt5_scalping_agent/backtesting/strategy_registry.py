"""Fixed-rule research strategy registry."""
from mt5_scalping_agent.backtesting.classic_baselines import AtrFilterStrategy, AtrFilteredMeanReversionStrategy, BollingerMeanReversionStrategy, DonchianBreakoutStrategy, DoubleBollingerBreakoutStrategy, MovingAverageCrossoverStrategy, NewYorkBollingerRsiReversalStrategy, NewYorkReversalStrategy, RsiTrendBreakoutStrategy
from mt5_scalping_agent.backtesting.london_range_breakout import LondonRangeBreakoutStrategy
from mt5_scalping_agent.backtesting.new_york_opening_range import NewYorkOpeningRangeBreakoutStrategy
from mt5_scalping_agent.backtesting.new_york_reentry import NewYorkBollingerReentryStrategy
from mt5_scalping_agent.backtesting.online_baselines import NewYorkOpeningRangeRetestStrategy, PreviousDayRangeBreakoutStrategy

STRATEGIES = {
    'london_range_breakout': LondonRangeBreakoutStrategy,
    'bollinger_mean_reversion': BollingerMeanReversionStrategy,
    'donchian_breakout': DonchianBreakoutStrategy,
    'moving_average_crossover': MovingAverageCrossoverStrategy,
    'atr_filter': AtrFilterStrategy,
    'new_york_reversal': NewYorkReversalStrategy,
    'new_york_bollinger_rsi_reversal': NewYorkBollingerRsiReversalStrategy,
    'new_york_opening_range_breakout': NewYorkOpeningRangeBreakoutStrategy,
    'double_bollinger_breakout': DoubleBollingerBreakoutStrategy,
    'rsi_trend_breakout': RsiTrendBreakoutStrategy,
    'atr_filtered_mean_reversion': AtrFilteredMeanReversionStrategy,
    'new_york_opening_range_retest': NewYorkOpeningRangeRetestStrategy,
    'previous_day_range_breakout': PreviousDayRangeBreakoutStrategy,
    'new_york_bollinger_reentry': NewYorkBollingerReentryStrategy,
}