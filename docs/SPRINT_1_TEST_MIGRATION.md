# Sprint 1 Test Migration

| test | failure | old assumption | correct semantics | classification | action |
|---|---|---|---|---|---|
| test_boundary_standardization_entries_dedup_and_outcomes | Expected a one-row move to be one minute on 30-minute data | Row count equals elapsed minutes | Exact event time plus horizon | LEGACY_TEST_DEFECT | Changed assertion to an exact 30-minute endpoint |
| test_attribution_and_path_metrics | Called path metrics without timestamps and expected row counts as minutes | One M5 row equals one minute | M5 timestamps produce 5-minute elapsed increments | LEGACY_TEST_DEFECT | Added timeline and asserted 5/10-minute threshold times |
| test_paths_are_direction_adjusted_and_use_future_only_as_outcomes | Close-only fixture failed new public-boundary validation | Research helpers may accept partial OHLCV | Public candle inputs must pass shared OHLCV validation | LEGACY_TEST_DEFECT | Migrated fixture to valid OHLCV |
| test_zero_path_is_missing_and_future_cannot_change_causal_features | Future close mutation created invalid OHLC geometry | Fixture validity was irrelevant | Validation remains true after future mutation | LEGACY_TEST_DEFECT | Mutated all OHLC fields consistently |
| exact_positions timezone arithmetic | NumPy object timestamps could not add minute timedelta | Zoned index converted safely through NumPy object arrays | Pandas timestamp arithmetic preserves timezone | CODE_REGRESSION | Replaced array arithmetic with per-offset DatetimeIndex lookup |
| canonical frozen cost fixture | Fixture lacked declared canonical round-trip cost | Components alone were accepted | Declared cost must match recomputed components | LEGACY_TEST_DEFECT | Added matching declared costs |

No failing test was changed to restore positional timing.
