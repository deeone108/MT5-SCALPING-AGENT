# Strategy 16 Research Brief

## Governance

This document prospectively freezes Strategy 16 before implementation and before any Strategy 16 development result is viewed. Development is restricted to accepted Dukascopy EURUSD M1 candles in `[2019-01-01, 2024-01-01)`. The post-selection 2024-2026 segment is prohibited. Strategy 15 and every earlier rejected strategy remain closed.

Strategy 16 is research-only and emits intents. It has no broker connection, order submission, DEMO mode, or LIVE mode.

## Hypothesis

Scheduled U.S. macroeconomic releases concentrate public information arrival around 08:30 America/New_York. When EURUSD makes an unusually large, directionally efficient five-minute displacement at that clock time and retains most of it during the next five minutes, incomplete interpretation and staged risk transfer may produce additional movement in the same direction after the first illiquid burst.

This is distinct from generic breakout, moving-average, channel, opening-range, compression-expansion, and mean-reversion strategies. The event clock and abnormal news-window displacement define the setup. The strategy never trades the first five minutes after 08:30.

The hypothesis is deliberately falsifiable. Research shows that much announcement price response can occur within minutes; therefore absence of after-cost continuation is a valid rejection, not a reason to loosen the rules.

## Causal data and clock

- Input: validated EURUSD bid-side UTC M1 OHLCV.
- Clock: `America/New_York` using IANA/zoneinfo DST rules.
- Eligible dates: Monday-Friday New York civil dates.
- Required exact M1 bars: every minute from 07:30 through 08:39 New York time, with no duplicate, missing, off-grid, or nonfinite bar.
- Pre-event baseline: twelve exact non-overlapping M5 bars spanning 07:30-08:29.
- Shock window: five M1 bars spanning 08:30-08:34.
- Stabilization window: five M1 bars spanning 08:35-08:39.
- Signal time: 08:39 M1 close.
- Entry: exact next M1 open at 08:40. A missing or delayed 08:40 bar invalidates the signal.
- No external economic calendar, survey expectation, realized release value, volume/order-flow claim, or future bar may be used.

## Frozen signal rules

Let `P0` be the 08:29 close. Let shock high/low/close be the aggregate high, low, and 08:34 close over 08:30-08:34. Let signed displacement `D = shock_close - P0`, magnitude `A = abs(D)`, and shock range `R = shock_high - shock_low`.

1. Compute the raw range of each of the twelve completed baseline M5 bars using linear quantiles.
2. Require `A >= 7.0 pips`.
3. Require `R >= max(2.0 * median_baseline_M5_range, baseline_M5_range_Q90)`.
4. Require directional efficiency `A / R >= 0.70`.
5. BUY direction is `D > 0`; SELL direction is `D < 0`. Zero displacement is forbidden.
6. BUY adverse shock excursion is `P0 - shock_low`; SELL adverse excursion is `shock_high - P0`. Require adverse excursion `<= 0.20 * R`.
7. During stabilization, BUY may not close below `P0 + 0.50*A`; SELL may not close above `P0 - 0.50*A`.
8. Maximum stabilization retracement from the shock close may not exceed `0.40*A`.
9. The 08:39 close must retain at least `0.70*A` from `P0` in the shock direction.
10. Reacceleration is required: BUY 08:39 close must exceed 08:37 close by at least 0.5 pip; SELL must be at least 0.5 pip below it.
11. Emit at most one intent per New York civil date. A risk- or economics-rejected intent consumes that date.

## Frozen trade plan

- BUY structural stop: the lower of the stabilization low and `P0 + 0.50*A`, minus 0.5 pip.
- SELL structural stop: the higher of the stabilization high and `P0 - 0.50*A`, plus 0.5 pip.
- Revalidate at the actual 08:40 entry.
- Actual stop distance must be between 5 and 15 pips.
- Target is exactly 2.25 times actual planned stop distance from entry.
- Actual remaining reward must be at least 8 pips.
- Under the frozen 1.9-pip stress reference, require `(reward - 1.9) / (risk + 1.9) >= 1.25`.
- Signal spread gate: no more than 10 points. Reference all-in cost: no more than 1.9 pips.
- One full position only; no pyramiding, averaging, partial exits, trailing stop, or break-even move.
- Exit priority on a shared candle: stop, then target, then time exit.
- Hard exit at the first M1 close at or after 10:00 New York time, never later than 80 elapsed minutes and never overnight.
- Fail the run loudly if an open position encounters an M1 gap greater than 60 seconds.

## Cost models

### Base news-window research cost

- Spread: 4 points (0.4 pip).
- Slippage: 2 points (0.2 pip).
- Commission: USD 2 per standard lot per side (0.4 pip round turn at one standard lot).
- Approximate all-in cost: 1.0 pip.

### Stress news-window research cost

- Spread: 10 points (1.0 pip).
- Slippage: 5 points (0.5 pip).
- Commission: USD 2 per standard lot per side (0.4 pip round turn).
- Approximate all-in cost: 1.9 pips.

These are conservative fixed research assumptions, not event-tick execution evidence. Tick replay with actual news-window bid/ask data remains mandatory before any DEMO eligibility.

## Primary development gates

All are frozen before results:

- Gross expectancy at least 3.0 pips/signal.
- Base net expectancy at least +2.0 pips/signal.
- Stress net expectancy at least +1.0 pip/signal.
- Median MFE at least 8 pips.
- At least 60% of trades have MFE greater than 6 pips.
- Median MFE / median adverse MAE at least 1.5.
- Base cost / median MFE no more than 0.15; stress cost / median MFE no more than 0.25.
- Between 40 and 180 completed signals in every development year.
- Maximum one emitted signal per New York date.
- Median holding duration between 10 and 60 minutes; hard maximum 80 minutes; no overnight trades.
- Minimum stop 5 pips; stop at least 2.5 times stress cost; reward at least 4 times stress cost; adjusted reward/risk at least 1.25.
- Base/stress profit factor at least 1.35/1.15.
- At least four of five positive years and at least 55% positive active months.

If any primary gate fails, mark Strategy 16 `REJECTED`; do not run bootstrap, neighborhoods, risk sizing, or 2024-2026.

## Conditional robustness gates

Only after every primary gate passes:

- 10,000 deterministic complete-block bootstrap resamples by UTC calendar day and ISO UTC week; seed `20260830`; 95% percentile intervals.
- Gross expectancy lower bound must exceed 1.5 pips for both block units.
- Stress net expectancy lower bound must be above zero for both block units.
- Effective sample size must satisfy `ceil(((1.96 + 0.84) * sample_standard_deviation_of_stress_net_pips / 1.0)^2)`.
- Report downside tail; risk-sized drawdown must be no more than 10% at 0.25% risk per trade.
- Strongest year may contribute no more than 40% of positive profit; top 10% of trades no more than 50%.
- Tick replay is a separate mandatory pre-DEMO gate.

Frozen one-factor neighborhoods, never used for selection:

- Minimum shock displacement: 6.0 and 8.0 pips.
- Shock/baseline median range multiple: 1.75 and 2.25.
- Minimum retained displacement at 08:39: 0.60 and 0.80.
- Maximum stabilization retracement: 0.30 and 0.50.
- Target reward/risk: 2.00 and 2.50.

Every neighbor must have positive stress expectancy; at least 8/10 must retain gross expectancy >=3.0 pips and stress net expectancy >=1.0 pip; median neighboring base/stress profit factor must be >=1.35/1.15. Never replace the frozen strategy with a neighbor.

## Evidence limitations

M1 bid candles cannot reproduce within-minute quote withdrawal, spread spikes, queue position, latency, or exact stop/target ordering. The shock detector is a price-based proxy and does not prove a scheduled announcement occurred. Results may therefore support rejection or further research only; they cannot authorize DEMO or LIVE trading.