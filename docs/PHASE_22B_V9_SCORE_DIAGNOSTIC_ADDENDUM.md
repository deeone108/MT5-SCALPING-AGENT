# Phase 22B v9 Score-Diagnostic Methodology Addendum

Phase 22B v9 supersedes rejected v8 only where explicitly authorized by `PH22B-SCORE-DIAGNOSTIC-AUTH-001`. All previously frozen specifications remain immutable history. The retained top-level methodology and task identifiers preserve the scientific identity; `specification_binding.version`, the canonical specification hash, and `methodology_amendment_v9` identify this superseding methodology version.

## Why amendment was required

The v7 diagnostic required 10,000 full M4 refits after within-stratum label permutations. At Phase 22B scale, continuous M4 controls vary inside those strata, so counts cannot reproduce the permuted exposure/control and exposure/outcome cross-products. There is no exact compressed equivalent under that permutation design. The diagnostic was supporting and non-gating. This replacement was selected and frozen before any Phase 22B market-data execution or outcome inspection.

## Frozen replacement

The replacement tests `H0: beta_exposure__WIDE = 0` against the two-sided alternative in the exact frozen raw-pip M4 population. It fits the restricted nuisance model and a weighted auxiliary residualization of exposure using the same pair-day weights, DGELSD path, rcond, condition ceiling, and frozen M4 column order. The efficient score is `U = sum(w*r*e)`.

UTC calendar day remains the cluster. The CR1 score variance is:

`V = [G/(G-1)] * [(N-1)/(N-K)] * sum_g(U_g^2)`

where `K` is the full unrestricted M4 column count. The statistic `Q=U^2/V` uses `chi-square(1)` and `scipy.stats.chi2.sf`. The specification freezes ordering, missingness, rank, singularity, finite-sample correction, numeric failures, provenance hashes, signed-zero handling, and deterministic replay.

## Non-gating guarantee

The score diagnostic is excluded from advancement, terminal classification, primary significance decisions, and every FDR family. It cannot override H_RAW, M0-M4 evidence, effect thresholds, or stability/confounding gates.

## Unchanged contract

Candidate, hypotheses, primary estimands, primary models, gates, thresholds, FDR families, pairs, direction, lookback, horizon, temporal partitions, data authority, holdout boundaries, scientific classifications, and all strategy/PnL/execution/LIVE and safety authorities are unchanged. Only 2019-2021 remains authorized; 2022 and 2023 remain locked; 2024+ remains forbidden.

## v8 clarification disposition

The tied-quintile, zero-spread, and streaming-context clarifications are carried forward unchanged. The four-versus-three metadata typo is corrected in v9. Bootstrap scalability provisions remain; permutation-specific provisions are superseded by the score diagnostic.
