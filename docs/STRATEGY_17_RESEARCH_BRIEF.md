# Strategy 17 Research Brief

## Governance

This document prospectively freezes Strategy 17 before implementation and
before any Strategy 17 development result is viewed. Development is limited to
accepted Dukascopy EURUSD M1 candles in `[2019-01-01, 2024-01-01)`. The
2024-2026 post-selection segment is prohibited. This is read-only research and
cannot submit orders.

## Hypothesis

London-session directional price discovery can sometimes persist into the New
York overlap after a contained pullback, producing a multi-hour EURUSD move
large enough for normal RoboForex ECN friction to be a minority of the planned
reward. This is a one-trade-per-day intraday continuation hypothesis, not an
M1 scalping, generic opening-range, compression-expansion, or scheduled-news
strategy.

## Frozen Design

- Use validated UTC M1 bid OHLCV and `Europe/London` civil time with DST.
- At exactly 11:00 London, require consecutive M1 candles from 06:00 through
  11:00. The first four completed hourly bars establish the London impulse;
  the fifth completed hourly bar establishes the pullback and reclaim.
- Require a 06:00-10:00 impulse of at least 25 pips, directional efficiency
  of at least 0.60, and a 10:00-11:00 pullback no deeper than 40% of the
  impulse. The 11:00 close must reclaim at least 80% of the impulse direction.
- Enter only on the exact next M1 open at 11:01. Emit at most one intent per
  London date. The rejected M1 intent still consumes the date.
- Use the pullback extreme plus a 1-pip buffer as the structural stop. Actual
  risk must be 12-35 pips. Set target at exactly 2R from actual entry; target
  must be at least 30 pips away.
- Exit at stop or target, otherwise at the first M1 close at or after 16:00
  London. No position can exceed 300 minutes or remain open overnight.
- No release calendar, realized macro value, order flow, volume, future data,
  trailing, averaging, partial exits, concurrent positions, or discretionary
  handling is allowed.

## Costs And Gates

Base costs are 1 spread point, 1 slippage point, and USD 2 per lot per side
(about 0.6 pips all-in). Stress costs are 3 spread points, 2 slippage points,
and the same commission (about 0.9 pips all-in). These use normal-session
broker evidence, not news-tick assumptions.

Primary development gates are frozen before results: gross expectancy at least
5 pips per trade, base/stress net expectancy at least 4/3 pips, median MFE at
least 20 pips, MFE above 12 pips on at least 65% of trades, median MFE/MAE at
least 1.5, 40-160 signals in each development year, at most one daily entry,
median holding 60-240 minutes, no overnight trade, base/stress PF at least
1.35/1.20, at least four positive years, and at least 55% positive active
months. Any primary failure rejects the candidate without robustness,
neighbourhood, risk-sizing, tick-replay, or post-selection work.

If every primary gate passes, use deterministic day/week block bootstrap,
effective-sample, downside, concentration, drawdown, and predefined frozen
neighbourhood diagnostics. Tick replay remains mandatory before any DEMO
eligibility.
