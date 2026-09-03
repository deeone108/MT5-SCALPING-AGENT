# Tick Replay Validation Design

## Scope and safety

This document specifies a future deterministic research simulator. It does not add MT5 order submission, DEMO execution, or LIVE execution. Tick replay is a validation stage between candle research and DEMO eligibility.

## Existing data and limitation

The repository currently has two read-only quote-snapshot datasets:

- `data/mt5_ticks/EURUSD_ticks.csv`: mixed MetaQuotes samples from Sunday opening, London, and New York captures.
- `data/mt5_ticks/roboforex_ecn/EURUSD_ticks.csv`: 3,600 RoboForex-ECN observations sampled approximately once per second during one New York hour.

These files contain observation time, broker tick time, bid, ask, and spread. They are suitable for spread/freshness calibration, but not historical tick replay: polling can repeat the same latest tick, misses events between samples, has no broker sequence number, and covers too little time and too few regimes.

Required additional data is a true event-level RoboForex ECN EURUSD bid/ask history, preferably millisecond resolution, spanning development and untouched forward periods across London/New York sessions, rollover, news/high-volatility intervals, DST transitions, and quiet markets. Provider provenance, timezone, contract specification, account type, and data hashes must accompany every file.

## Canonical input

A replay source exposes a bounded, single-pass iterator of immutable records with:

- `symbol`
- `event_time_utc`
- `received_time_utc` when available
- `bid` and `ask`
- optional last price, volume, source flags, and source sequence
- provider and file/run identifier

The adapter must reject nonpositive prices, `ask < bid`, naive timestamps, mixed symbols, conflicting duplicate sequence values, and observations outside the requested half-open period.

## Ordering, duplicates, and stale ticks

1. Preserve provider sequence when supplied; otherwise order by event time and stable source row number.
2. Exact duplicate records may be de-duplicated and counted. Same key with different prices is an error requiring quarantine.
3. Time moving backwards beyond an explicit tolerance is an error, never silently sorted away.
4. A tick is stale when event-to-replay-clock age exceeds the frozen manifest limit. Stale ticks can update diagnostics but cannot trigger a signal, entry, or exit fill.
5. Gaps and connection-loss intervals are explicit events. The simulator cannot interpolate unseen prices.

## Clock and candle construction

The replay clock advances only from accepted tick events. A causal bar builder creates bid-side M1 OHLC and records the contemporaneous ask/spread path plus tick count and completeness. An M1 bar becomes visible to a strategy only after its end time. M5 features are built only from five completed eligible M1 bars.

A strategy developed on M1 data is evaluated once after a bar closes using only bars and indicators available then. Any resulting intent is timestamped at the close and becomes fill-eligible only on the first accepted tick at or after `intent_time + configured_latency`. No tick from the signal bar's future or from the fill interval is visible during signal calculation.

## Simulated market-order fills

- BUY entry fills against ask; SELL entry fills against bid.
- Configured adverse slippage is applied in addition to the observed executable side, never substituted for spread.
- Latency is a frozen fixed value or a seeded distribution recorded in the manifest.
- A gap fills at the first eligible executable quote, not the requested pre-gap price.
- Initial validation may model all-or-none fills, but the event/result schema must support rejected and partial fill fragments before partial fills are enabled.
- Margin, volume step, minimum/maximum volume, market hours, stops level, freeze level, spread ceiling, and risk approval are checked before a simulated submission.

## Stops, targets, and exits

- A long position exits at bid. Its stop activates when `bid <= stop`; its target activates when `bid >= target`.
- A short position exits at ask. Its stop activates when `ask >= stop`; its target activates when `ask <= target`.
- Sequential ticks resolve activation order, eliminating M1 simultaneous-SL/TP ambiguity.
- Stop exits fill at the first available executable price and can gap adversely.
- Target behavior must be frozen as either market-on-trigger or limit semantics. The initial conservative model should use market-on-trigger and never improve a fill using an unseen price.
- Commission is booked per actual filled lot per side. Spread and slippage remain separate economics fields.
- Rollover/swap is applied only when a position crosses the broker's documented charge boundary; it must not be guessed.

## Position state machine

Permitted deterministic transitions are:

`FLAT -> INTENT -> RISK_REJECTED | VALIDATED -> SIMULATED_SUBMITTED -> REJECTED | PARTIALLY_FILLED | OPEN -> EXIT_PENDING -> CLOSED`

Every transition records time, triggering event, quantities, prices, costs, reason, and risk decision. Invalid or duplicate transitions fail closed. One component owns position state; strategies cannot mutate it.

## Outputs and reconciliation

A replay produces:

- run manifest and input hashes
- accepted/rejected/duplicate/stale/gap tick counts
- strategy intents and risk decisions
- order/fill/position transition journal
- full trade economics compatible with `BacktestTrade`
- candle-versus-tick result comparison
- latency, spread, slippage, gap, and rejection diagnostics
- invariant checks for position quantity, cash/equity, and cost accounting

## Validation plan before implementation

1. Unit-test ordering, duplicates, stale ticks, crossed quotes, and gaps.
2. Test causal M1/M5 construction at exact boundaries and DST changes.
3. Test BUY/SELL fills and stop/target activation on executable quote sides.
4. Test latency without future access and deterministic seeded slippage.
5. Test gap-through-stop, rejected order, partial-fill state transitions, and restart recovery.
6. Compare replayed bars with source M1 archives for covered periods and explain differences.
7. Re-run only a development-approved candidate; tick replay must never become a parameter-search loop.

## Implementation boundary

The future implementation should live behind research-only interfaces such as `TickSource`, `ReplayClock`, `CausalBarBuilder`, `FillModel`, and `ReplayPositionBook`. It must not import or call MT5 `order_send`. A separate future DEMO adapter may consume the same validated intent and risk contracts only after tick replay, integration tests, and explicit approval.