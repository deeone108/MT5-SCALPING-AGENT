# Phase 22B v12 Production Numerics Addendum

v12 removes all production dependence on fixture-only expanded DGELSD results. Primary conditioning comes from A eigenvalues; fallback conditioning and bread come from the stacked QR-factor SVD. Both paths have production-computable coefficient and covariance envelopes.

Named coefficient, linear-contrast, attenuation, direct pair-day, ratio, quantile, and p-value calculations propagate certified intervals. Scientific thresholds are unchanged and ambiguous boundary overlap fails closed. Expanded results remain no-data fixture references only; compressed replay remains byte-identical to itself.

A matrix-only preflight selects solver paths before scientific statistics. No more than 100/10,000 fallbacks per model population are permitted. The fixed benchmark includes the worst allowed fallback count, and full-workload extrapolation assumes that maximum rather than a fixture-observed rate.

No market data was accessed. v6-v11 remain immutable. Scientific, temporal, data, strategy, PnL, execution, LIVE, and safety authority are unchanged.
