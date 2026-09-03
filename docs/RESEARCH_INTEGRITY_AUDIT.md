# Research Integrity Audit

Date: 2026-09-03

Scope: engineering correctness only. No strategy, architecture, production
code, or tests were changed.

## Decision summary

Research results are not ready to be treated as stable. Several outputs named
in elapsed minutes are calculated by row offset. The shared validator rejects
duplicates and disorder but does not enforce M1 cadence, so missing candles can
silently lengthen nominal horizons.

1. **P0: row horizons are labelled as clock horizons.** Phase 19A/19B and 20A
   outcomes and paths use positional M1 offsets.
2. **P0: Phase 21A/21B has a 5x unit mismatch on complete data.** Residuals are
   M5, but horizons advance 5-60 rows. Therefore 'change_60m', 'pos+60', and a
   60-row path represent 300 elapsed minutes. Threshold times are M5-bar counts
   labelled as minutes.
3. **P1: EURUSD commission contradicts its evidence.** Config stores USD 2.00
   per lot per side while its text says USD 3.00, rounded up from USD 3.00.
4. **P1: Phase 19A/19B/20A read a generated cost report**, not canonical config.
   No hash ties it to config, contracts, or calibration reports.
5. **P1: local reports mix evidence generations.** Smoke, checkpoint,
   development, post-selection 2024-2026, diagnostic, and incomplete Phase 21B
   artifacts coexist without immutable run identity.

## Horizon inventory

| Location | Row versus timestamp behaviour | Consequence |
|---|---|---|
| 'causal_bars' | Timestamp resample; incomplete M5/M15 buckets dropped | Adjacent retained rows may not be time-adjacent |
| 'add_pair_features' | Prior-row M5/M15 rolling windows | Causal, but duration expands across gaps |
| 'structural_events' | Prior 12 and next two M5 rows | Confirmations can jump over missing buckets |
| 'attach_forward_outcomes' | Next N M1 rows | Missing M1 stretches minute-labelled outcomes |
| 'conditional_edge_validation.attach_path' | Integer M1 offsets | Path and extrema times have row semantics |
| Phase 19B lead/lag | Shift on available M15 rows | One bar need not be 15 minutes |
| 'build_observations' | Every fifth M1 row plus offsets | Gaps alter grids, paths, runs, and extrema times |
| 'common_residuals' | Timestamp-aligned complete-M5 join | Same-time join is sound; gaps remain |
| 'relative_value_discovery.outcomes' | Advances N M5 rows | Labels understate elapsed time by 5x or more |
| Phase 21B and 'path_metrics' | 'pos+60' and next 60 M5 rows | 300-minute endpoint/path labelled 60m |
| 'causal_volatility_regimes' | Row-based M1 ATR lag/rolling | Causal; duration depends on density |
| Indicators/baselines | Backward row windows | No look-ahead found; density-dependent duration |
| Backtest engine/newer strategies | Timestamp iteration; several candle-gap limits | Safer behaviour to preserve |

A shift used only to exclude the current observation is causally sound. A row
is not a minute until cadence is proved.

## Research integrity

Strengths include explicit half-open development ranges ending 2024-01-01,
archive hashes in several manifests, timestamp-aligned cross-pair factors,
complete composite buckets, elapsed-time event deduplication, and future
mutation causality tests. Shared validation rejects duplicates, disorder,
missing timestamps/prices, invalid OHLC geometry, and negative volume.

Material gaps:

- Cadence is not proved before positional horizon calculations.
- Research entry points do not consistently use shared validation.
- Phase 21B has null target/common-change and maximum-widening medians beside
  other metrics. 'INCOMPLETE_EVIDENCE' is appropriate; it is not final evidence
  and lacks a Phase 19A-21A-style manifest.
- Sibling outputs lack a shared run ID or manifest digest.
- Horizon tests use regular indexes and do not challenge gaps, duplicates, or
  exact endpoint timestamps.

## Cost consistency

Canonical intent is 'config/cross_pair_cost_models.json'. The backtester receives
separate spread, slippage, and commission components.

| Pair | Base spread/slippage | Stress spread/slippage | Commission USD/side | Generated base/stress pips |
|---|---:|---:|---:|---:|
| EURUSD | 2 / 1 | 4 / 2 | 2.00 | 0.70 / 1.00 |
| GBPUSD | 2 / 1 | 5 / 2 | 2.85 | 0.87 / 1.27 |
| USDJPY | 3 / 1 | 8 / 2 | 2.00 | 1.039172 / 1.639172 |
| USDCAD | 4 / 1 | 5 / 2 | 2.00 | 1.055004 / 1.255004 |

The derivative report matches numeric config, but EURUSD narrative does not.
If USD 3.00 is authoritative, both EURUSD figures are 0.20 pip too low. General
runners accept independent CLI costs, and Strategy 15-17 contain separate
scenarios; outputs are incomparable without explicit input provenance.

## Stale or mixed reports

Local 'reports/' contains 2006 and 2026 runs, 2019-2023 development work,
annual diagnostics through 2026, smoke/profile/checkpoint/final files,
alternative costs, progress/log files, and incomplete Phase 21B output. Only
'reports/.gitkeep' is tracked. Ignored state is still risky because some runners
read a report as input. Every citable artifact needs schema version, run ID,
completion state, evidence role, period, code/data hashes, and cost-model hash.

## Sprint-two regression tests

### Time alignment

1. Assert outcome value and exact endpoint timestamp at +5/+10/+15/+30/+60.
2. Require M5 confirmations exactly +5 and +10 minutes after a break.
3. Assert +60 minutes on M5 residuals selects 12 bars, not 60.
4. Assert Phase 21B endpoint and threshold-time units.
5. Cover London/New York DST boundaries with fixed UTC duration.
6. Require exact cross-pair contributor timestamps.

### Missing candles

1. Remove M1 inside each outcome: reject, mark missing, or use exact target
   timestamp; never substitute the next row.
2. Require complete elapsed lookbacks or explicitly name row windows.
3. Prevent incomplete M5/M15 bars bridging confirmations or lags.
4. Distinguish expected FX closures from in-session gaps; do not synthesize
   flat candles.
5. Verify post-entry maximum candle-gap enforcement.

### Duplicate timestamps

1. Duplicate start, event, path, and endpoint; all public research entry points
   must reject before lookup or array construction.
2. Use conflicting duplicate OHLC and prove no implicit selection.
3. Duplicate one cross-pair input and reject join expansion.
4. Reject duplicates at annual-file boundaries.

### Costs and provenance

1. Recompute costs from canonical config and fixed contract fixtures.
2. Make commission derivation structured and machine-checkable.
3. Mutate config after report generation and require stale-hash failure.
4. Require schema/run/completion/code/data/cost metadata on final reports.
5. Prevent checkpoint, smoke, or incomplete artifacts satisfying final loaders.

## Sprint-two recommendation

Define elapsed-time versus row-window contracts; enforce them on all
minute-labelled outcomes; resolve EURUSD commission; make config the sole cost
authority; add report run identities; and implement the regression matrix
before regenerating results.

Treat Phase 19-21 results dependent on positional minute labels as provisional.
