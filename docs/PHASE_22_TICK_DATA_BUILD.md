# Phase 22 True-Tick Data Build

Status: `HUMAN_GATE_REQUIRED_SOURCE_ACCESS`. Run: `phase22_data_build_20260905T150855Z_715c0bc`. This sprint stopped before any network request, pilot download, dependency installation, normalization, or research calculation.

## Immutable scope

- Data engineering only; no Phase 22A research, Strategy 22, signal, PnL, optimization, MT5 connection, or order submission.
- Universe: EURUSD, GBPUSD, USDJPY, USDCAD.
- Development interval: `[2019-01-01T00:00:00Z, 2024-01-01T00:00:00Z)` only.
- Frozen pilot, declared before download: EURUSD `[2019-01-07T00:00:00Z, 2019-01-14T00:00:00Z)`.
- No 2024+ acquisition or access is authorized.

## Source verification

The mechanism currently callable from this Python project is pinned package `dukascopy-python==4.0.1` (MIT code license; installed module SHA-256 `0e72e2c35a7ab3bb08c2aba7fae66090b20a6c8d0dcdbba0e6ba89ab0cd8141bf`). Its implementation calls:

`https://freeserv.dukascopy.com/2.0/index.php`

with `path=chart/json3`, `interval=TICK`, cursor `last_update` in Unix epoch milliseconds, `time_direction=N`, maximum page limit 30,000, and instrument names `EUR/USD`, `GBP/USD`, `USD/JPY`, and `USD/CAD`. It supplies browser-like User-Agent, Host, and Referer headers and a random JSONP callback. Responses are uncompressed JSONP arrays containing millisecond timestamp, bid price, ask price, bid volume, and ask volume. These are quotes, not trades. The library divides both volume fields by 1,000,000. It retries exceptions up to the configured limit (default seven) with fixed one-second waits; it has no bounded exponential backoff, explicit HTTP status validation, Retry-After handling, immutable raw response capture, or documented rate limiter.

Dukascopy documents historical all-ticks as tick-after-tick history and its official JForex `IHistory` API exposes historical ticks. However, that official authenticated SDK/export mechanism is not implemented or configured in this Python repository.

## Legal/source-access gate

Dukascopy's current Terms of Use state that automated tools, scrapers, bots, or code may not acquire website data without prior express written consent. They allow limited personal, non-commercial downloading but restrict transfer, redistribution, competing use, and unreasonable load. The free-tools disclaimer describes the data as Dukascopy's discretionary assessment, provided AS IS, and requires clear attribution if publicly used.

The MIT license of `dukascopy-python` licenses the client code only; it does not grant rights to Dukascopy market data or authorize automated access. No provider consent, licensed API credential, JForex export authorization, or separately agreed data-feed contract is recorded in this repository. Therefore the available `freeserv` automation cannot be used safely merely because the project owner authorized the sprint.

Primary sources checked 2026-09-05:

- <https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/>
- <https://www.dukascopy.com/trading-tools/disclaimer>
- <https://www.dukascopy.com/wiki/en/forex-cfds/jforex/historical-tester/>
- <https://www.dukascopy.com/wiki/en/development/strategy-api/historical-data/history-ticks/>

This is an engineering/compliance gate, not legal advice.

## Valid resolutions

Provide one of:

1. Dukascopy's express written consent for automated historical tick acquisition and local non-commercial research storage through the identified endpoint, including acceptable request rate; or
2. authorized Dukascopy/JForex credentials and confirmation that official `IHistory`/Historical Tester export may be automated and stored for this research; or
3. provider-supplied files obtained through an authorized manual/export workflow, together with applicable terms and provenance; or
4. explicit approval of another licensed source, which would require a source-methodology addendum before download.

After resolution, record the authorization evidence without secrets, freeze the precise mechanism and safe request policy, implement the raw-preserving daily checkpoint pipeline, add Parquet support, and run only the frozen pilot. Bulk acquisition remains gated on pilot validation and measured disk projection.

## Current data-build state

- Pilot tick count: not available; no source request made.
- Pilot quality/compression/gap/duplicate statistics: not available.
- Full pair/year coverage: 0 of 20.
- Total acquired Phase 22 ticks: 0.
- Dataset root hashes: not created.
- Replay validation: not run because no tick archive exists.
- Available disk at gate: 535,511,883,776 bytes (498.73 GiB); storage sufficiency cannot be decided until an authorized pilot measures bytes per tick.
- Existing one-second polling captures remain excluded; they are not true event ticks.
