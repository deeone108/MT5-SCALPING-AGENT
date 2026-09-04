# Phase 21C Prospective One-Leg Hypothesis

Status: frozen before any 2024+ access. This document defines future validation; it reports no trading performance.

## Lineage and scope

- Phase 21A parent: `reproduction_20260903T224000Z_860ce89`.
- Phase 21B parent: `phase21b_completion_20260904T213000Z_c051246`.
- Phase 21B specification: commit `a30322bd35abdb2dc909862fe63a8e01d6f54604`, SHA-256 `a64a6fa831e69ed4471ef510715c6bd3c22f2a0984998240ff86e769809465f8`.
- Pair universe: EURUSD, GBPUSD, USDJPY and USDCAD. All four remain included and receive equal weight in aggregate inference.
- Method A is the signal representation. Method B is robustness evidence only and cannot generate entries.
- Phase 21C uses existing 2019–2023 evidence only. It does not open or test a holdout.

## Frozen hypothesis

> When a target FX pair enters an already-defined Phase 21A extreme relative-value residual state, the target pair subsequently tends to move in the direction that reduces the initial residual dislocation.

No wording, feature, threshold, pair, session, volatility filter, holding period, stop, target or sizing rule may be selected after holdout access.

## Entry event and overlap

Eligibility is exactly the existing Phase 21A construction: the frozen four-pair universe and USD orientation; causal M5 returns; prior-window causal standardisation; Method A residual equal to the target USD-oriented z-score minus the equal-weight mean of the other three available pair z-scores; causal prior-window residual percentile; first entry into an existing `90-95`, `95-99`, or `99-100` extreme bucket; and the existing per-target-pair 60 elapsed-minute deduplication. No portfolio-level allocation or cross-pair overlap rule is introduced.

## Direction

Let `r_t0 = z_target,t0 - common_t0` and let `USD_SIGN` be `-1` for EURUSD/GBPUSD and `+1` for USDJPY/USDCAD. Holding the common component constant, reducing `|r_t0|` requires an oriented target move of `-sign(r_t0)`. Therefore raw-pair exposure is derived, never pair-hardcoded:

`direction = -sign(r_t0) * USD_SIGN[pair]`

`+1` denotes long and `-1` denotes short. A zero or non-finite residual is ineligible.

## Timing and exit

The event becomes known at exact timestamp `t0`. Candidate entry is the exact M1 observation at `t0 + 1 elapsed minute`, the first permissible observation after the event. If it is absent, status is `MISSING_EXACT_ENTRY`; no later bar substitutes. The sole exit is the exact observation 60 elapsed minutes after entry (`t0 + 61 minutes`). If absent, status is `MISSING_EXACT_EXIT`. Path statistics require every intervening exact M1 timestamp; a gap is `MISSING_EXACT_PATH`. Unavailable events do not enter outcome inference.

There is no take-profit, stop-loss, trailing stop, residual exit, dynamic exit or same-bar execution.

## Exposure and costs

Exposure is fixed at one standard lot solely as a normalized measurement convention. There is no compounding, account-relative sizing, Kelly sizing, volatility sizing or leverage optimization. Results are also reported in native pips.

The single source of truth is `config/cross_pair_cost_models.json`. Primary inference deducts the frozen pair-specific STRESS all-in round-trip cost, containing spread, slippage and commission. BASE all-in cost is secondary only. Costs cannot be tuned. At freeze time the stress/base costs in pips are EURUSD 1.20/0.90, GBPUSD 1.27/0.87, USDJPY 1.639172/1.039172 and USDCAD 1.255004/1.055004.

## Outcomes

For each eligible event:

- `gross_directional_pips = direction * (exit_price - entry_price) / pip_size`;
- `stress_cost_pips` is the canonical pair STRESS round-trip cost;
- `net_directional_pips = gross_directional_pips - stress_cost_pips`.

The primary aggregate metric is the equal-weight mean of the four pair-level mean net directional pips. This prevents event-count differences from implicitly changing pair weights.

Frozen secondary outcomes are median net pips, STRESS-cost win rate, gross mean pips, mean cost pips, profit factor, median and p90 adverse excursion, median and p90 favourable excursion, maximum consecutive losing events, event count, and availability rate. BASE net pips are secondary cost evidence. Adverse p90 is the lower tenth percentile of signed MAE; favourable p90 is the upper ninetieth percentile of MFE.

## Prospective inference and classifications

The primary aggregate uses a deterministic calendar-trading-day block bootstrap with seed `21003` and 10,000 replicates. A replicate samples observed calendar-day blocks with replacement and preserves all same-day cross-pair events; it then calculates each pair mean and their equal-weight mean. The 95% percentile CI and one-sided test `H0: mean <= 0`, `H1: mean > 0` use alpha 0.05. Pair-level CIs may be supporting evidence but are not additional primary tests.

Before testing, require at least 500 eligible aggregate events and at least 75 for every pair. Otherwise classify `INSUFFICIENT_HOLDOUT_SAMPLE`, not failure.

With sufficient data, classify `PROSPECTIVE_HYPOTHESIS_PASSED` only when every condition holds:

1. Equal-weight aggregate mean STRESS-net pips is greater than zero.
2. At least three of four pair means are greater than zero.
3. The sum of the four pair means remains positive after inclusion of every negative pair; operationally, no negative pair outweighs the combined positive pair means.
4. The aggregate bootstrap 95% CI has a lower bound greater than zero.
5. The one-sided bootstrap p-value is at most 0.05.
6. The minimum sample requirements are met.
7. No pair contributes more than 50% of the sum of absolute pair-level mean effects.
8. The ten largest absolute event net effects contribute no more than 20% of total absolute event net effect.

If sample requirements pass but any other condition fails, classify `PROSPECTIVE_HYPOTHESIS_FAILED`.

## Safety and change control

The evaluator accepts an explicit half-open range `[start, end_exclusive)` and rejects any range extending beyond 2023 unless a future caller explicitly authorizes holdout access. Phase 21C executes synthetic tests only. It contains no MT5 integration, broker connection, order submission, strategy object, trade intent or live execution path. The isolated external-research stash is outside this lineage.
