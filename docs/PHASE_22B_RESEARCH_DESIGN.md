# Phase 22B Mechanism-Validation Research Design

Status: **FROZEN PENDING INDEPENDENT REVIEW**  
Task: `PH22B-RL-001`

Phase 22B asks whether `P22A_SPR_ABS_15s_60s` reflects a genuine raw-price microstructure relationship or a normalization/confounding mechanism. The raw-pip contrast is primary because Phase 22A reported a large negative current-spread-unit contrast alongside a small positive raw-pip contrast. Current-spread-normalized evidence cannot establish genuineness alone.

The machine-readable specification in `research/phase22b_spec.json` is authoritative. It fixes the exposure, outcomes, controls, interactions, temporal gates, bootstrap, multiplicity, effect-size requirements, confounding rules, terminal classification hierarchy, seeds and leakage tests before data access.

No Phase 22B data was accessed to create this design. All 2019-2023 data remains locked. The 2023 stage is explicitly an internal temporal replication, not a pristine holdout, because Phase 22A already exposed aggregate 2023 diagnostics.

This phase contains no strategy, trading rules, PnL, costs, optimization, ML or execution.