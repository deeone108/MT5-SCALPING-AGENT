# STRATEGY_15_RESEARCH_BRIEF

## Status

This is a pre-implementation economic specification, not a strategy. No Strategy 15 hypothesis, rules, code, registry placeholder, or backtest has been created. Review is required before Phase C.

## Economic problem

Strategy 15 must identify fewer EURUSD intraday opportunities whose repeatable gross move is materially larger than transaction friction. It must earn its edge at constant unit exposure before risk sizing can improve or damage portfolio survival.

The closed New York paths generated 13,846 and 25,148 fixed-lot signals in 2019-2023, but only `0.2833` and `0.2218 pip/signal` gross expectancy against `0.7 pip` modeled cost. Median favorable and adverse excursions were similar, holding periods were only 3-5 minutes, and every year was net-negative. Strategy 15 therefore needs a distinct market mechanism, stronger opportunity asymmetry, substantially lower turnover, and better gross capture.

## Frozen economic scenarios

For one standard EURUSD lot, one pip is USD 10 under the project symbol model.

| Scenario | Spread | Slippage | Round-trip commission | All-in cost |
| --- | ---: | ---: | ---: | ---: |
| Base research model | `0.2 pip` | `0.1 pip` | `0.4 pip` | `0.7 pip` |
| Predeclared stress model | `0.4 pip` | `0.2 pip` | `0.4 pip` | `1.0 pip` |

The base spread is the captured New York p95; the stress spread is the captured maximum, and stress slippage is twice the current assumption. RoboForex currently publishes EURUSD ECN average spread `0.1 pip`, commission `20/mio`, one-lot size 100,000 EUR, and `0.00001` tick size in its [contract specification](https://roboforex.com/forex-trading/trading/specifications/card/pro-stan-ecn/EURUSD/).

These are research scenarios, not execution evidence. The spread capture covered one hour of one-second quotes, slippage is unmeasured, and commission is modeled from the published schedule.

## Required economic profile

These thresholds are anchored to cost coverage and estimation margin, not back-solved to make an old strategy pass.

| Dimension | Pre-registered requirement before a Strategy 15 backtest |
| --- | --- |
| Gross edge | Point estimate at least `1.5 pips/signal`: more than 2x base cost and 1.5x stress cost. |
| Statistical economic floor | Day/week block-bootstrap 95% lower bound for gross expectancy above `1.0 pip`, equivalently a stress-cost net lower bound above zero. |
| Net margin | Point expectancy at least `+0.8 pip` under base cost and `+0.5 pip` under stress. |
| Gross movement | Median candle-level MFE at least `4.0 pips`; at least 60% of signals must exceed `3.0 pips` MFE. |
| Opportunity asymmetry | Median MFE divided by median adverse-MAE magnitude at least `1.5`. |
| Cost/opportunity | Base cost no more than 20% of median MFE; stress cost no more than 25%. |
| Frequency | Design for approximately `250-500` completed signals/year and at most two entries/day. Frequency is not a substitute for per-signal edge. |
| Holding period | Expected median in the `15-120 minute` range, hard intraday exit by 240 minutes, and no overnight exposure unless independently justified before testing. |
| Stop economics | Stop must be structural and at least `4 x` stress cost, currently at least `4.0 pips`, so friction is no more than 25% of planned risk. |
| Reward economics | Planned reward at least `6 x` stress cost and cost-adjusted planned reward/risk at least `1.5`. |

For planned stop `S`, reward `R`, and all-in cost `C`, evaluate:

- cost-adjusted reward/risk: `(R - C) / (S + C)`;
- break-even win rate: `(S + C) / (R + S)`;
- reward needed for assumed win probability `p` and desired net margin `mu`: `((1 - p) * S + C + mu) / p`.

The final stop, target, and holding rule must come from the causal market hypothesis. These equations reject economically cramped plans; they do not define an entry signal.

## Evidence requirements

- Development data is exclusively `[2019-01-01, 2024-01-01)`. Do not load 2024-2026 during design or selection.
- Freeze hypothesis, rationale, exact rules, features, timeframes, session, exits, frequency, costs, and gates before the first result.
- Replace IID promotion inference with a predeclared day/week block bootstrap and report active days, weeks, months, years, directions, and causal regimes.
- Do not reuse a flat 300-trade gate. For minimum meaningful stress-net margin `0.5 pip`, use `n_eff >= ceil(((1.96 + 0.84) * s_net / 0.5)^2)`. The rejected paths' `5.5-6.5 pip` dispersion implies roughly 950-1,340 IID-equivalent observations; serial clustering can require more raw trades.
- If five development years cannot supply the required effective sample, classify the evidence as insufficient rather than relaxing the gate.
- Require after-cost profit factor at least `1.25` under base cost and `1.10` under stress, at least 4/5 positive years, at least 55% positive active months, and realistic risk-sized maximum drawdown no greater than 10%.
- Limit concentration: strongest year no more than 35% of positive net profit and top 10% of trades no more than 50% of the positive net-profit pool.
- Run the unit-exposure gate first, then a separately manifested realistic risk-sized portfolio simulation.
- Predeclare cost stress and parameter-neighborhood cases. The frozen candidate must pass without selecting the best neighboring result.
- Only after all development gates pass may 2024-2026 be used once as post-selection robustness evidence. True bid/ask tick replay remains mandatory before DEMO eligibility.

## Hypothesis constraints

Strategy 15 must belong to a genuinely new family with an independently stated reason for the edge to exist. It must not be a Bollinger mean-reversion variation, RSI-threshold variation, minor ATR/session adjustment, parameter tune, or combination intended to rescue a rejected New York reversal.

Before Phase C, introduce a versioned registry/gate schema that can honestly store an unimplemented `PROPOSED` strategy with zero experiments and the new economic, block-bootstrap, monthly, concentration, and neighborhood gates. Do not put fake implementation or evidence values into registry schema v1.

## Stop point

No Strategy 15 implementation or historical test is authorized by this brief. The next action is user review of the economic requirements.
