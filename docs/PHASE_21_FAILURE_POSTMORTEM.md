# Phase 21 Failure Post-Mortem

Status: immutable descriptive closure of accepted run `phase21d_20260904T230000Z_886b656`. This uses only already-generated Phase 21D artifacts; no market data was rerun and no rule was changed or searched.

## Verdict and lineage

- Phase 21A: `MEAN_REVERSION_PHENOMENON`.
- Phase 21B: `MIXED_CONVERGENCE_PHENOMENON`.
- Phase 21C: `PROSPECTIVE_HYPOTHESIS_FROZEN` at commit `420b7fc9ea274ced5dd44bb6dfe244fbe3f64533`, specification SHA-256 `59606899783e6cc3d35f49a6437013dd483da890cda58db16b674f831017900e`.
- Phase 21D: `PROSPECTIVE_HYPOTHESIS_FAILED`.
- Phase 21 family: `CLOSED_FOR_THIS_HYPOTHESIS`.

The verdict is final. The 2024-01-01 22:04 UTC through 2026-08-21 20:59 UTC archive is exposed evidence for this lineage and must never again be described as pristine untouched holdout. No Phase 21 horizon, pair, session, volatility state, residual threshold, Method A definition, entry, exit, stop, target, or cost scenario may be varied to rescue it.

## Accepted run provenance

Runner commit: `886b6566e21cf02ea0df4a178da09f48fb19af67`. Canonical cost-model SHA-256: `7c2937ffdb91233cec875895c2f42efc247bd242ef117cc74c7540420cb4faba`. `completion_validation.json` reports `valid: true`, no invalid components, and independently recomputes the failed verdict. The run used no MT5 or broker execution.

## C1-C8

| Criterion | Frozen requirement | Result | Exact reason |
|---|---|---|---|
| C1 | Equal-weight aggregate STRESS-net mean > 0 | **FAIL** | `-1.116578` pips. |
| C2 | At least three of four pair means > 0 | **FAIL** | Zero of four were positive. |
| C3 | No negative pair outweighs combined positive pair means | **FAIL** | All four pair means were negative. |
| C4 | Bootstrap 95% CI lower bound > 0 | **FAIL** | `[-1.298087, -0.935122]`, wholly below zero. |
| C5 | One-sided bootstrap p-value <= 0.05 | **FAIL** | `p = 1.0`. |
| C6 | >=500 available events overall and >=75 per pair | **PASS** | 25,464 overall; 6,203-6,682 per pair. |
| C7 | No pair >50% of summed absolute pair mean effects | **PASS** | Maximum 28.7306% (USDCAD). |
| C8 | Ten largest absolute event effects <=20% of total | **PASS** | 0.7846%. |

## Economics, paths, and concentration

Equal-weight gross mean was `+0.224466` pips, equal-weight STRESS cost `1.341044` pips, and equal-weight net mean `-1.116578` pips. The calendar-day bootstrap used 10,000 replicates and seed 21003; its 95% CI was `[-1.298087, -0.935122]` and one-sided p-value `1.0`.

| Pair | Available / eligible | Availability | Gross | Cost | Net | Win | PF | Median / p90 MAE | Median / p90 MFE | Max loss run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 6,323 / 6,784 | 93.20% | +0.353456 | 1.200000 | -0.846544 | 45.22% | 0.8153 | -4.90 / -17.00 | 5.30 / 17.08 | 14 |
| GBPUSD | 6,256 / 6,834 | 91.54% | +0.029907 | 1.270000 | -1.240093 | 46.37% | 0.7842 | -6.30 / -20.90 | 6.60 / 20.50 | 15 |
| USDJPY | 6,682 / 7,074 | 94.46% | +0.542697 | 1.639172 | -1.096475 | 46.47% | 0.8582 | -8.50 / -29.20 | 8.50 / 29.90 | 12 |
| USDCAD | 6,203 / 6,796 | 91.27% | -0.028196 | 1.255004 | -1.283200 | 44.37% | 0.7287 | -5.00 / -17.00 | 5.20 / 16.30 | 14 |

Pair contribution was EURUSD 18.9540%, GBPUSD 27.7655%, USDJPY 24.5499%, and USDCAD 28.7306%. Top-five/top-ten absolute event contribution was 0.4801%/0.7846%; top-five/top-ten trading-day contribution was 2.8104%/5.0720%. Failure was broad, not concentrated.

## Time stability and availability

| Period | Equal-weight net pips | Available events |
|---|---:|---:|
| 2024 | -1.089845 | 9,553 |
| 2025 | -1.161679 | 9,917 |
| Partial 2026 through 21 August | -1.083735 | 5,994 |

Every pair-year mean was negative. Of 27,488 eligible events, 25,464 were available (92.64%): 227 lacked exact entry, 266 exact exit, and 1,531 complete exact path. Availability passed the frozen gate and does not explain failure.

## Descriptive failure mechanism

- `COST_EROSION` is primary: +0.2245 gross pips could not cover 1.3410 pips of STRESS friction.
- `NO_GROSS_EDGE`: GBPUSD gross was nearly zero and USDCAD negative; positive gross effects were economically too small.
- `PAIR_INSTABILITY`: gross effects ranged from -0.0282 to +0.5427 and no pair survived costs, though this was not concentration.
- `TEMPORAL_INSTABILITY`: no evaluated year produced positive net results.

`CONCENTRATION`, `INSUFFICIENT_BREADTH`, and `STATISTICAL_UNCERTAINTY` do not apply: C6-C8 passed and the CI is precisely below zero.

## Source fingerprints and closure policy

`manifest.json` `081f30da17c941f2c413de1f31c32352293a3139fd1515fe8119afbc88b00f5f`; `event_outcomes.json` `2d602a0efcc3ea6e7f1a89a686d1d2384b1f8763e6aaf056a38c2cb432427947`; `pair_results.json` `304412a2c0d577feb4889111ece9e8f19734ccd888ee61a96118e6b8ad09534c`; `year_results.json` `d107fab5db6482cc3df3bbd23b707c09ecf70b6ad06baec29ea2d07043cd78ec`; `bootstrap.json` `6e950d1e9fc74f629d0a4e29176eb4cca6c38360d5c5b5455871a4d93b712dec`; `concentration.json` `b03b5088d85dcb6ea25d847223575d7111115a97fe629180377347f2473b0116`; `success_criteria.json` `7198376c06ef8687aba46251a50ebc4a58b78efd2102d3abfd5b04a3ca795908`; `completion_validation.json` `25d768d0e0d31e632e0ab380be070707465bc363eb50f0f19b0f663abb6d4a0e`.

2019-2023 remains development/discovery data. The exposed 2024-2026 archive is robustness evidence only for independently developed future hypotheses. Strongest prospective validation must use new data gathered after freeze. MFE, MAE, paths, BASE costs, or subsets must not be used to invent a Phase 21 variant.
