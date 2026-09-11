# Phase 22B v10 Bootstrap Implementation Addendum

Phase 22B v10 supersedes v9 only for deterministic implementation of the already-frozen daily-block bootstrap. It does not change any bootstrap population, draw, seed, replicate count, statistic, covariance, threshold, gate, or scientific decision.

The expanded implementation repeatedly materialized millions of rows and invoked DGELSD tens of thousands of times. v10 freezes per-UTC-day weighted sufficient statistics. Exact v7 day draws become integer day multiplicities. Each replicate aggregates the corresponding normal system, solves the same mathematical WLS objective using a frozen positive-definite solver, and constructs CR1 meat by adding one-copy cluster-score outer products once per logical copy. Logical N and G retain copied-block semantics.

Point estimates and all non-bootstrap primary fits remain on frozen DGELSD. Pair-day/normalization bootstraps use frozen day/pair/exposure sums and counts. One interaction-model bootstrap fit supplies all preregistered level contrasts.

Expanded-DGELSD synthetic fixtures remain the mandatory reference. Draws, ranks, failures and decisions must match exactly; numerical quantities must meet the frozen 32-ULP tolerance, with fail-closed behavior near every decision boundary. A 10,000-replicate, 1,096-day, K=80 single-thread benchmark and full-workload extrapolation must pass before data access.

No market outcomes were inspected. v6-v9 remain immutable. Only 2019-2021 remains authorized; 2022/2023 remain locked and 2024+ forbidden. Strategy, PnL, execution and LIVE remain unauthorized.
