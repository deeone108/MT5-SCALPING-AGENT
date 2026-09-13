# BOT-01 Repository Component Audit

Baseline: `54cf5e49404534b9efdb992a804d83dc6e3c5944`  
Role: QA / Code Reviewer  
Scope: tracked source, tests, configuration, governance, and dataset metadata only. No market rows, broker orders, strategy evaluation, or Phase 22 research were accessed.

## Result

The repository has a tested candle backtester, fourteen registered fixed-rule research strategies, deterministic risk sizing/limits, read-only MT5 market-data access, data validation, and mature research-governance tooling. It does not yet contain a broker request builder, DEMO executor, position/order reconciliation, durable bot state, production telemetry, or an implemented runtime AI trading agent. Existing orchestration agents govern engineering and research; they are not market-decision agents.

## Component matrix

| Component | Location | Status | Tests | Reusable | Blocker | Target |
|---|---|---|---|---|---|---|
| Strategy registry / fixed rules | `backtesting/strategy_registry.py`, strategy modules | IMPLEMENTED_AND_TESTED | PASS | Yes | Common compatibility/config contract incomplete | BOT-02 |
| Runtime trend signal generator | `strategies/trend_scalper.py` | IMPLEMENTED_AND_TESTED | PASS | Yes | No bot coordinator | BOT-06 |
| Signal/trade models | `domain/models.py`, `backtesting/engine.py` | IMPLEMENTED_AND_TESTED | PASS | Yes | Research intent is not a broker order | BOT-09 |
| Candle backtester | `backtesting/engine.py` | IMPLEMENTED_AND_TESTED | PASS | Yes | One strategy/symbol per run | BOT-07 |
| Costs/accounting/reporting | `backtesting/engine.py`, `backtesting/reporting.py`, cost config | IMPLEMENTED_AND_TESTED | PASS | Yes | XAUUSD calibration and tournament ledger absent | BOT-05/BOT-08 |
| Historical data adapters | `data/` | IMPLEMENTED_AND_TESTED | PASS | Yes | Acquisition is outside BOT-01 | BOT-05 |
| MT5 market-data adapter | `data/mt5_client.py` | IMPLEMENTED_AND_TESTED | PASS | Yes | Read-only; limited reconnect semantics | BOT-15 |
| Risk engine/state | `risk/engine.py`, `risk/state.py` | IMPLEMENTED_PARTIAL | PASS | Yes | Margin, duplicate, kill-switch and account-mode gates absent | BOT-12 |
| Repository orchestrator | `orchestration/`, `agents/`, `governance/` | IMPLEMENTED_AND_TESTED | PASS | Engineering governance | Not a trading-agent runtime | BOT-10 |
| Trading-agent runtime | `agent/__init__.py` | STUB_ONLY | Import only | No | No coordinator/evidence boundary/lifecycle | BOT-10 |
| Broker execution | `execution/__init__.py` | STUB_ONLY | None | No | No request/check/send/fill/close/retry code | BOT-16 |
| Portfolio management | `portfolio/__init__.py` | STUB_ONLY | None | No | No position registry/reconciliation | BOT-13 |
| Telemetry | `monitoring/__init__.py`, research reports/run state | IMPLEMENTED_PARTIAL | Research only | Partly | No bot decision/trade/health telemetry | BOT-18 |
| Restart/recovery | research runtime supervisor only | PRESERVED_RESEARCH_ONLY | Supervisor tests | Limited | No broker/risk/strategy recovery | BOT-17 |
| XAUUSD support | generic point/tick-value risk primitives | IMPLEMENTED_PARTIAL | Generic only | Partly | No dataset, symbol mapping or broker calibration | BOT-05 |
| External repository work | preserved-research index only in tracked baseline | PRESERVED_RESEARCH_ONLY | Not established | Undetermined | Implementations unavailable in tracked baseline | BOT-03/BOT-04 |
| Windows background runtime | `orchestration/runtime_supervisor.py` | PRESERVED_RESEARCH_ONLY | PASS | Avoid initially | Suspended research component, not bot runtime | BOT-19 |
| Safety authority | governance policy/state | IMPLEMENTED_AND_TESTED | PASS | Yes | Executor-bound DEMO/LIVE gates absent | BOT-14/BOT-16 |

## Strategy system

The registry contains 14 concrete classes rather than subclasses of one shared base class. `SignalProposal` and `TradeIntent` form the practical boundary. Stops and targets are explicit and simulated entry is delayed to the next candle. Strategies mix stateless indicators with session/range state; session helpers exist in `data/sessions.py`.

All requested implementations exist: ATR-filtered mean reversion, Bollinger mean reversion, New York Bollinger-RSI reversal, New York reversal, New York opening-range breakout, RSI trend breakout, and double-Bollinger breakout. BOT-02 must inventory exact inputs, warmups, timeframes, state, exits, configuration, and instrument constraints without changing rules.

## Backtester

Reusable: next-bar intents, conservative candle execution, stop/target and holding/gap exits, spread, slippage, per-side commission, risk-percent or diagnostic fixed-lot sizing, cost reconciliation, equity curve, drawdown, and MAE/MFE. It deterministically consumes validated chronological OHLCV. Year aggregation and exports exist around the engine.

Needed for the tournament: a standardized multi-strategy/multi-instrument harness and eligibility contracts. The engine runs one strategy/symbol at a time and models spread cost rather than replaying bid/ask paths. Broker-native XAUUSD monetary accounting remains unverified.

## Historical-data metadata

No rows were opened. Tracked manifest filenames and the preserved-research index show EURUSD legacy Dukascopy/HistData M1 metadata (including 2003-2006 and later subsets) and EURUSD/GBPUSD/USDJPY/USDCAD 2019-2023 metadata plus the preserved MT5 Phase 22 tick dataset. These assets remain governed and inactive; this audit does not validate row coverage.

No tracked XAUUSD dataset manifest was found: `XAUUSD_HISTORICAL_DATA_MISSING`.

## MT5 and XAUUSD

`MT5ReadOnlyClient` implements initialize, shutdown, terminal status, account info, symbol selection/info, latest tick, historical rates, and historical ticks. It contains no `order_check`, `order_send`, positions/orders/deal-history, or reconciliation API and no automatic reconnect loop. Order submission is absent. State additionally records `execution_api=false`, `order_submission=false`, and `live_execution_authorized=false`.

Risk sizing accepts broker `point`, `tick_size`, `tick_value`, and volume bounds/step, reusable for metals. BOT-05 must verify symbol aliases, digits/point/pip conventions, contract/tick values, cost configuration, minimum stops, strategy thresholds, and session assumptions for XAUUSD.

## Risk controls

Implemented and tested: percentage risk, symbol-aware sizing, maximum lot, broker min/max/step, maximum open positions, total and same-symbol exposure, spread limit, daily/weekly loss, drawdown, consecutive losses, hourly/daily trade limits, stale-data rejection, directional stop/target geometry, and minimum reward/risk.

Partial: typed models reject many malformed values, but there is no complete broker-quote integrity gate. Missing: margin/free-margin validation, duplicate-order prevention, operational kill switch, DEMO-account enforcement, and executor-bound LIVE blocking. Governance blocks execution, but an execution layer does not yet exist.

## Agents, execution, telemetry, recovery

Implemented agents are role charters and a manifest/hash/gate/worktree orchestrator. No market/context/risk/execution consensus agent exists. Deterministic strategy eligibility, risk approval, and execution validation must remain code-owned; AI may later summarize evidence or recommend only among authorized actions.

Execution and portfolio packages are empty stubs. Fill handling, SL/TP modification, strategy close, retry/requote, reconnect, position discovery, duplicate prevention, and crash-safe bot recovery are missing. The Phase 22B runtime supervisor is preserved inactive and should not force multiprocessing; initially prefer one controlled Python bot runtime.

Telemetry is fragmented: backtest reports and governance manifests provide research provenance, but structured bot decisions, trade journal, metrics, error telemetry, signal logs, and health status are absent.

## Coverage and next action

Coverage is strong for strategies, indicators, candle backtesting, costs, risk, read-only MT5 data, validation, research, and orchestration. Missing execution, agent, portfolio, XAUUSD, restart, and telemetry tests reflect missing implementation.

BOT-01 passes. Exact next authorized action: `BOT-02_COMPLETE_EXISTING_STRATEGY_INVENTORY`.
