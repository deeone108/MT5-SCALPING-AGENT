# BOT-02 Existing Strategy Inventory

Baseline: `01a809805cc134ab37e4d558daade76d711cd1ef`  
Scope: source, registry, configuration, and synthetic/unit tests only. No market data, backtest, optimization, or strategy mutation.

## Contract and lifecycle

The active backtest registry is `STRATEGIES` in `src/mt5_scalping_agent/backtesting/strategy_registry.py`. It maps 14 stable names to concrete callable classes. There is no common base class or formal protocol. Every registered class exposes `__call__(history: pandas.DataFrame) -> TradeIntent | None`, declares `uses_latest_candle_only = True`, and declares `required_history_bars`. `CandleBacktester` supplies completed history and executes a returned intent on the next candle. Every intent carries BUY/SELL, stop loss, and take profit; strategies do not directly enter, close, size, or contact a broker.

The separate research registry records all 14 as `REJECTED` with completed evidence. Therefore “implemented and tested” below means software maturity only. None is DEMO-eligible, LIVE-eligible, or approved for trading. BOT tournament eligibility must remain separate from historical research status and requires later authorized gates.

## Registered strategies

All time/session references below are UTC unless stated. “Any candle” means the class does not enforce a frequency; historical runners commonly supply M1, so explicit timeframe compatibility remains a BOT-06/BOT-07 validation item.

| Registry name / implementation | Inputs and warm-up | Signal and configuration | Exit / SL / TP | Time/session/instrument | State | Maturity |
|---|---|---|---|---|---|---|
| `london_range_breakout` / `LondonRangeBreakoutStrategy` | time, high, low, close; streaming, 1 declared bar | Break completed 00:00–07:00 range during 07:00–12:00; frozen dataclass session/RR config | Range opposite edge; configurable RR target | Intraday candles; UTC; price-generic | Daily range and one-trade flag | IMPLEMENTED_AND_TESTED; research REJECTED |
| `bollinger_mean_reversion` / `BollingerMeanReversionStrategy` | close; 21 bars | Close outside 20-bar mean ±2 population SD; constants embedded | 1 SD stop; mean target | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `donchian_breakout` / `DonchianBreakoutStrategy` | high, low, close; 21 bars | Close beyond prior 20-bar channel; constants embedded | Channel-width stop; 2R target | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `moving_average_crossover` / `MovingAverageCrossoverStrategy` | close; 21 bars | 5/20 simple-mean crossing; constants embedded | Distance to slow mean; 2R | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `atr_filter` / `AtrFilterStrategy` | high, low, close; 21 bars | Close beyond prior channel by 25% width; name is historical—implementation uses channel width, not ATR | Channel-width stop; 2R | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED; naming mismatch NOTE |
| `new_york_reversal` / `NewYorkReversalStrategy` | time, close; 21 bars | Bollinger mean reversal only 12:00–17:00; constants embedded | Parent 1 SD stop; mean target | Intraday UTC; fixed UTC window is not DST-aware | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `new_york_bollinger_rsi_reversal` / `NewYorkBollingerRsiReversalStrategy` | time, close; 21 bars | Parent reversal plus RSI(14) ≤30 BUY / ≥70 SELL; constants embedded | Parent 1 SD stop; mean target | Intraday UTC; fixed UTC, not DST-aware | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `new_york_opening_range_breakout` / `NewYorkOpeningRangeBreakoutStrategy` | time, high, low, close; 21 bars | 12:00–13:00 range break through 17:00 aligned with 20-bar mean; dataclass times/RR | Opposite range edge; configurable RR | Intraday UTC; fixed UTC, not DST-aware | Daily range and one-trade flag | IMPLEMENTED_AND_TESTED; REJECTED |
| `double_bollinger_breakout` / `DoubleBollingerBreakoutStrategy` | close; 21 bars | Continuation beyond outer 20-bar 2-SD band; constants embedded | Inner 1-SD band; 2R | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `rsi_trend_breakout` / `RsiTrendBreakoutStrategy` | high, low, close; 22 bars | Prior-20 channel break, 20-bar mean direction, RSI(14) ≥55/≤45 | Opposite channel edge; 2R | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `atr_filtered_mean_reversion` / `AtrFilteredMeanReversionStrategy` | high, low, close; 22 bars | Parent Bollinger reversal only if ATR(14) ≤2× prior-20 median true range | Parent 1 SD stop; mean target | Any candle; no session; price-generic | Stateless | IMPLEMENTED_AND_TESTED; REJECTED |
| `new_york_opening_range_retest` / `NewYorkOpeningRangeRetestStrategy` | time, high, low, close; 21 bars | 12:00–12:30 break, retest and re-break through 17:00 with 20-bar mean alignment | Opposite range edge; implementation hard-codes 2R | Intraday UTC; fixed UTC, not DST-aware | Daily range, break/retest, one-trade flag | IMPLEMENTED_AND_TESTED; REJECTED; config RR field is validated but unused |
| `previous_day_range_breakout` / `PreviousDayRangeBreakoutStrategy` | time, high, low, close; streaming, 1 declared bar | Break completed prior UTC-day range during 07:00–17:00 | Opposite prior-day edge; 2R | Intraday UTC; price-generic | Current/prior range and one-trade flag | IMPLEMENTED_AND_TESTED; REJECTED |
| `new_york_bollinger_reentry` / `NewYorkBollingerReentryStrategy` | time, high, low, close; 22 bars | Prior close outside 2-SD band, current re-entry, RSI exhaustion; dataclass session/RR/ATR multiplier | ATR(14) multiple stop; configurable RR | Intraday UTC; fixed UTC, not DST-aware | Daily one-trade flag | IMPLEMENTED_AND_TESTED; REJECTED |

All 14 use the same engine-owned entry semantics: signal after a completed candle, pending intent filled no earlier than the following candle. Normal exits are engine-owned stop, target, optional time/gap exits, or end-of-data liquidation. These registered classes do not emit custom close instructions.

## Configuration and compatibility findings

- Four registry entries have typed frozen dataclass configuration: London range breakout, New York opening-range breakout, New York opening-range retest, and New York Bollinger re-entry. The remaining ten embed constants in code and expose no uniform configuration surface.
- The registry stores classes, not factories or descriptors. It has no machine-readable columns, timeframe, session, statefulness, supported-symbol, or parameter metadata.
- No registry class validates an instrument. Most arithmetic is price-scale generic, but fixed thresholds and cost expectations were researched for EURUSD. Session rules assume timezone-aware timestamps and several use fixed UTC “New York” hours rather than DST-aware New York local time.
- Stateful daily strategies require a fresh instance per independent run and chronological uninterrupted input. Reusing instances across symbols or folds would leak state.
- `required_history_bars=1` for the two streaming range strategies describes callback slice size, not total warm-up: London needs the completed Asian range and prior-day breakout needs a prior UTC day.
- `NewYorkOpeningRangeRetestConfig.target_reward_risk_ratio` is not used by its implementation, which hard-codes `2`. This is a deterministic contract defect for a later implementation milestone; BOT-02 does not change it.
- `AtrFilterStrategy` is named as ATR-filtered but implements a 25%-of-channel-width breakout threshold and calculates no ATR. Preserve the rule; clarify naming/metadata later rather than silently changing behavior.

## Implemented but not in `STRATEGIES`

| Implementation | Status / reason not active | Target |
|---|---|---|
| `TrendScalper` + `TrendScalperBacktestStrategy` | IMPLEMENTED_AND_TESTED; separate M1/M5 proposal system, not research registry entry | BOT-06 |
| `CompressionExpansionControlledContinuationStrategy` | IMPLEMENTED_AND_TESTED, research registry strategy 15 `REJECTED`; intentionally excluded | BOT-03/BOT-04 evidence inventory |
| `ScheduledMacroShockContinuationStrategy` | IMPLEMENTED_AND_TESTED, research registry strategy 16 `REJECTED`; intentionally excluded | BOT-03/BOT-04 |
| `LondonNewYorkIntradayContinuationStrategy` | IMPLEMENTED_AND_TESTED frozen Strategy 17; unregistered | BOT-03/BOT-04 |
| `LondonAsianRangeFailedAuctionStrategy` | IMPLEMENTED_AND_TESTED frozen Strategy 18; unregistered | BOT-03/BOT-04 |
| `EfficientTrendScalperBacktestStrategy` | IMPLEMENTED_AND_TESTED specialized adapter; not a standalone registry candidate | BOT-06 |

No duplicate registry keys or duplicate class bindings were found. There is no code-level deprecated marker. Research `REJECTED` is a scientific lifecycle classification, not source deprecation.

## Gaps mapped to existing milestones

- BOT-03/BOT-04: reconcile preserved/external/frozen strategy provenance and decide what is eligible for the bot inventory without reviving rejected research.
- BOT-05: create verified XAUUSD instrument/cost/data contracts; none of the 14 is currently XAUUSD-qualified.
- BOT-06: define the common strategy contract and adapters, including timeframe, columns, warm-up, instance lifecycle, and deterministic configuration.
- BOT-07: build the multi-strategy/multi-instrument tournament harness around the existing engine.
- BOT-09: keep proposal/intent/exit semantics deterministic and separate from broker orders.
- BOT-10: allow agents to consume only explicit registry metadata and evidence; agents must not reinterpret `REJECTED` strategies as approved signals.

## Conclusion

BOT-02 is complete as an inventory. It does not promote or authorize any strategy. No strategy may enter DEMO merely because its implementation imports or its unit tests pass.
