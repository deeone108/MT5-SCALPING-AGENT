# Phase 20A Intraday Price-Path and Liquidity Behaviour Discovery

Phase 20A starts a new descriptive research family after Phase 19 was closed. It measures causal M1 price paths sampled only after completed M5 bars for EURUSD, GBPUSD, USDJPY, and USDCAD in `[2019-01-01, 2024-01-01)`.

It has no strategy, order, position, stop, target, sizing, PnL, equity, MT5, or candidate-registry capability. It uses fixed 5/15/30/60 minute windows, fixed percentile buckets, frozen broker-cost models, deterministic local-civil-time DST-aware transition markers, 60-minute primary-event de-duplication, 5,000-replicate trading-day block bootstrap, and Benjamini-Hochberg FDR at 5%.

Its final classification can only describe market behaviour. It cannot create Strategy 19 or Strategy 20, nor advance to another phase without human review.