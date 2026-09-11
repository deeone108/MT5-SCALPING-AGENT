# Phase 22B v11 Numerical Equivalence Addendum

Phase 22B v11 supersedes only v10's fixed 32-ULP expanded/compressed comparison. Fixed componentwise ULP distance is inappropriate because normal-equation forward error scales with condition number and near-zero components may have large ULP distances despite small normwise error.

v11 freezes condition-aware normwise forward-error and backward-error bounds. Exact schedules, multiplicities, logical counts, ranks, failures, percentile indices, p-value counts, FDR membership, and scientific decisions must still match. Any result within its propagated numerical bound of a scientific threshold fails closed.

When conditioning makes the SPD primary path unreliable, v11 deterministically switches to a compressed per-day QR representation. Multiplicity scales each day's canonicalized R factor by sqrt(m), and the stacked factor system is solved through the frozen DGELSD path. CR1 continues to use v10's logical day-copy sufficient statistics, not QR pseudo-clusters. No outcome-favorable solver choice or third fallback exists.

Production replay remains byte-identical within the compressed implementation. Expanded DGELSD is required for no-data equivalence fixtures only. The v10 performance gate includes fallback cost.

No market data was accessed. v6-v10 remain immutable. No scientific, temporal, data, safety, strategy, PnL, execution, or LIVE authority changed.
