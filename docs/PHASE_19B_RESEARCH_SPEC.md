# Phase 19B Conditional Edge Validation

## Scope
This is a post-discovery diagnostic for the Phase 19A structural-event family. It uses only EURUSD, GBPUSD, USDJPY, and USDCAD data in `[2019-01-01, 2024-01-01)`. It is not untouched validation and must not be used to approve a trading strategy.

## Boundaries
- No data from 2024 or later is loaded.
- No MT5 access, execution, trade simulation, PnL, equity curve, or research-candidate registry entry is permitted.
- Existing Phase 19A definitions are retained: M5 displacement, structural break, acceptance, rejection, leave-one-out USD factor, and event deduplication.

## Diagnostics
The runner records raw displacement, structural-break, acceptance, and rejection event families; direction-adjusted paths at 1 to 60 minutes; MFE/MAE and their ordering; leave-one-year-out means; session summaries; opportunity-to-cost ratios; and predefined M15 lead-lag correlations for 1, 5, 10, 15, and 30 bars.

## Decision rule
This phase can only diagnose or close an event family. It cannot create Strategy 19 or modify any strategy rules. The current result is `CLOSE_FAMILY`: the Phase 19A GBPUSD acceptance observation is not a cost-aware, predictive trading signal.