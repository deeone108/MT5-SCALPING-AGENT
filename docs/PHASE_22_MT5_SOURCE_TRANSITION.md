# Phase 22 MT5 Historical Source Transition

Status: **MT5_PHASE22_HISTORICAL_SOURCE_APPROVED**

The manual JForex bulk route is **ABANDONED_FOR_OPERATIONAL_COMPLEXITY**. This is an operational decision, not a scientific invalidation. All JForex pilot artifacts, manifests, hashes, reports, exporter code, and importer code remain preserved.

## Read-only safety and connection

The probe used MetaTrader5.copy_ticks_range with COPY_TICKS_ALL through MT5ReadOnlyClient. The implementation contains no order, position, pending-order, or trade-request API. Connection succeeded to RoboForex Ltd / RoboForex-ECN with MetaTrader5 package 5.0.6090. No account identifier or credentials were recorded.

MT5 time and time_msc are interpreted as UTC. Returned fields were: time, bid, ask, last, volume, time_msc, flags, volume_real. Bid and Ask were positive and non-crossed in every pilot response.

## Frozen pilot: 2019-01-07 through 2019-01-14 UTC

| Pair | Ticks | First tick epoch ms | Last tick epoch ms |
|---|---:|---:|---:|
| EURUSD | 580,212 | 1546819200257 | 1547251139395 |
| GBPUSD | 547,647 | 1546819202097 | 1547251139485 |
| USDJPY | 578,538 | 1546819200147 | 1547251132833 |
| USDCAD | 452,307 | 1546819260291 | 1547251139175 |

The last ticks occur on Friday 2019-01-11 because the requested interval ends before the next market reopening.

## Development-period depth

Small read-only samples returned meaningful ticks for every pair in 2019, 2020, 2021, 2022, and 2023. The oldest confirmed sample tick was EURUSD at 2019-01-02T10:00:00.088Z. Late-development samples continued through:

| Pair | Latest confirmed 2023 tick UTC |
|---|---|
| EURUSD | 2023-12-29T23:54:16.678Z |
| GBPUSD | 2023-12-29T23:54:48.550Z |
| USDJPY | 2023-12-29T23:54:51.239Z |
| USDCAD | 2023-12-29T23:54:50.023Z |

These are confirmed probe boundaries, not claims that no earlier or later broker tick exists. No 2024+ data was used.

## EURUSD source characterization

This is descriptive only; broker-native MT5 and JForex quotes are not expected to match.

| Metric | RoboForex MT5 | JForex |
|---|---:|---:|
| Tick count | 580,212 | 787,718 |
| Spread p50/p90/p95/p99 (pips) | 0.4 / 0.6 / 0.6 / 1.3 | 0.3 / 0.5 / 0.5 / 1.1 |
| Inter-tick p50/p90/p95/p99 (ms) | 190 / 1,760 / 3,130 / 8,681 | 154 / 1,259 / 2,195 / 5,545.84 |
| Gaps over 1 second | 96,968 | 102,692 |
| Gaps over 60 seconds | 8 | 2 |
| Maximum gap (ms) | 97,639 | 62,576 |
| Subsecond timestamp fraction | 99.9016% | 99.9096% |

## Automated archive

scripts/download_mt5_phase22_ticks.py manages an immutable 240-unit pair/month manifest for the half-open interval 2019-01-01 through 2024-01-01.

Each unit stores the exact structured NumPy response as compressed NPZ, provider-neutral normalized Parquet, metadata and SHA-256 hashes. Validation covers Bid/Ask, monotonic ordering, duplicate timestamps, distinct same-time quotes, flags, and timestamp precision. Writes use temporary artifacts and atomic manifest replacement. Existing artifacts are never overwritten.

Prepare or inspect the manifest:

    .\.venv\Scripts\python.exe scripts\download_mt5_phase22_ticks.py --prepare
    .\.venv\Scripts\python.exe scripts\download_mt5_phase22_ticks.py --status

Retrieve one monthly unit:

    .\.venv\Scripts\python.exe scripts\download_mt5_phase22_ticks.py --next

The five-year acquisition was not started during source approval.
## Dataset completion

The 2019-2023 build is **PHASE_22_DATA_READY**: 240/240 monthly units validated, 0 failed, covering 618,387,844 ticks. Semantic validation and 20/20 deterministic replay samples passed. Full statistics and hierarchical hashes are recorded in [PHASE_22_MT5_DATASET_COMPLETION.md](PHASE_22_MT5_DATASET_COMPLETION.md).
