# Strategy 18 Research Brief

## Governance

Strategy 18 is a proposed four-pair research candidate only. It applies the
same frozen rules to EURUSD, GBPUSD, USDJPY, and USDCAD using their separate
2019-2023 Dukascopy M1 archives and frozen RoboForex ECN base/stress costs.
No 2024-2026 data may be loaded. No broker execution is permitted.

## Hypothesis

After a quiet Asian-session range, a London-session excursion that closes back
inside that range can represent a failed liquidity auction rather than accepted
new value. A confirmation close inside the range may permit a limited intraday
move toward the opposite side of the range. The design seeks one structural
opportunity per London date, rather than high-frequency mean reversion.

## Frozen Rules

- Use completed UTC M1 bid OHLCV converted with `Europe/London` civil time.
- Form the Asian reference range from every exact M1 bar from 00:00 through
  05:59 London. Missing or nonconsecutive required bars reject the date.
- Between 07:00 and 09:00 London, identify the first completed M5 close that
  is at least 8 pips outside the Asian high or low. This is the sweep direction.
- In the following three completed M5 bars, require a close at least 1 pip back
  inside the Asian range. Enter in the opposite direction only at the next M1
  open after that confirmation close. Emit at most one intent per London date;
  a rejected intent consumes the date.
- Stop is the sweep extreme plus a 1-pip buffer, mirrored by direction. Actual
  entry risk must be 8-25 pips. Target is exactly 2R and at least 16 pips away.
- Exit at stop or target, otherwise at the first M1 close at or after 12:00
  London. Maximum holding time is 240 minutes. No overnight position.
- At entry, use the pair's frozen stress cost. Require reward minus stress cost
  divided by risk plus stress cost to be at least 1.50. Reject any spread above
  that pair's frozen stress spread or any all-in cost above its frozen stress
  round-trip cost.
- No Bollinger bands, RSI, ATR threshold, moving average, macro calendar,
  volume, order flow, future bar, averaging, trailing, partial exits, concurrent
  position, or discretionary condition is allowed.

## Frozen Development Gates

Each pair is evaluated separately and the candidate is not promoted by selecting
the best pair. Every pair must have 50-220 accepted trades per year, positive
gross expectancy of at least 3 pips per trade, base net expectancy of at least
1.5 pips, stress net expectancy of at least 0.75 pips, base/stress profit
factor of at least 1.30/1.15, at least four positive years, and at least 55%
positive active months. Median MFE must be at least 8 pips and at least 1.5
times median MAE. The development result must be profitable after stress costs
on the aggregate of all four pairs without any pair being negative.

Only if every primary gate passes may block bootstrap, concentration, drawdown,
and frozen-neighborhood diagnostics run. A primary failure rejects the candidate
without adjustment, parameter selection, post-selection data, demo, or live
trading.
