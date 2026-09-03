# Phase 21A Relative-Value Discovery

Development-only descriptive research over four Dukascopy pairs in `[2019-01-01, 2024-01-01)`. It measures causal standardized USD-oriented M5 residuals against a contemporaneous leave-one-out common component. It has no strategy, execution, PnL, sizing, or MT5 capability. Phase 19 and Phase 20A remain closed.

## PRE-REPRODUCTION METHODOLOGY ADDENDUM

Frozen at 2026-09-03T19:48:19.7131260Z, before accessing corrected Phase 21A
results. These definitions must not change after reproduction begins.

Method A remains primary and unchanged.

Method B is robustness evidence only. For each target pair, fit causal rolling
multivariate OLS of its existing USD-oriented causally standardized return on
an intercept and the three other pairs. Fit on the previous 20 trading days,
excluding the current observation, with no imputation. The residual is observed
minus predicted. Missing contributors or insufficient valid prior history make
the residual unavailable. Method B cannot replace Method A and PCA is forbidden.

Use the existing causal volatility percentile, calculated against the previous
20 trading days excluding the current observation. Fixed regimes are LOW below
30 percent, NORMAL from 30 to below 70, HIGH from 70 to below 90, and EXTREME
from 90 percent.

For every event at t0, inspect residuals only at exact elapsed M5 timestamps
t0+5 through t0+60 minutes. Never bridge or impute a missing timestamp. Record
path completeness and mark calculations requiring missing observations
unavailable.

Time to 75, 50, and 25 percent is the first actual elapsed minute where absolute
residual is at most 0.75, 0.50, or 0.25 times its initial magnitude. A zero
cross is the first exact timestamp where residual is zero or changes sign from
the initial residual. Unreached thresholds are explicitly NOT_REACHED.

At each valid path observation, widening is absolute residual minus initial
absolute residual. Maximum widening is the greater of its path maximum and
zero; report its magnitude and actual elapsed minute. No convergence within 60
minutes means the 50 percent threshold was not reached. No definition,
threshold, window, pair universe, or method may be selected after results are
observed.
