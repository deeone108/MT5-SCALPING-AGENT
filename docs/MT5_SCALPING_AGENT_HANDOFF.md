# MT5 Scalping Agent Handoff

## Purpose and safety status
- This is a safety-first EURUSD research/backtesting project, not a live-trading system.
- The typed runtime configuration defaults to BACKTEST. Order submission remains blocked; all MT5 work performed so far is read-only.
- No strategy is approved for paper trading or live trading.
- Git is not installed on this machine, so there is no commit history available.

## Current architecture
- `src/mt5_scalping_agent/config/settings.py`: typed configuration and strict BACKTEST safety gate.
- `src/mt5_scalping_agent/data/mt5_client.py`: read-only MT5 connection, symbol, tick, account, and candle access.
- `src/mt5_scalping_agent/data/historical_range.py`: explicit UTC range loader. It was fixed to filter results strictly to the requested `[start, end)` interval because MT5 had returned a recent fallback candle for unavailable historical dates.
- `src/mt5_scalping_agent/data/local_archive.py`: validated local annual M1 loader. It rejects date ranges crossing the 2019 provider boundary and derives causal M5 candles only when constituent completeness satisfies the selected policy.
- `src/mt5_scalping_agent/data/quality.py` and `data/sessions.py`: archive-quality auditing and DST-aware London/New York diagnostic sessions.
- `src/mt5_scalping_agent/backtesting/engine.py` and `backtesting/reporting.py`: single-position, next-candle-entry backtester with explicit gross/cost/net trade economics, MAE/MFE, mark-to-market state, and an explicit research-only fixed-lot sizing mode. Risk-percent sizing remains the default.
- `src/mt5_scalping_agent/risk/state.py`: reusable simulated risk state for streaks, trade rates, daily/weekly loss, exposure, and mark-to-market drawdown. It has no broker execution capability.
- `src/mt5_scalping_agent/research/manifest.py`: deterministic run manifests, data/code hashes, atomic checkpoints, and strict resume compatibility validation.
- `src/mt5_scalping_agent/research/continuous_evaluation.py`: split-isolated 2019-2023 continuous diagnostics by calendar, direction, DST-aware session, and causal volatility regime.
- `src/mt5_scalping_agent/research/signal_economics.py` and `scripts/run_signal_economics.py`: hard-scoped constant-1-lot diagnostics for exactly the two rejected New York leaders on 2019-2023 only. They report USD/pip economics, MFE/MAE, planned distances, causal regimes, DST-local New York subsections, and balance-independent decay.
- `src/mt5_scalping_agent/research/statistical_robustness.py`: deterministic bootstrap, consistency, concentration, drawdown, and downside-tail diagnostics.
- `src/mt5_scalping_agent/research/registry.py` and `config/research_registry.json`: machine-readable history and decisions for exactly 14 existing strategies. All remain `REJECTED`.
- `src/mt5_scalping_agent/backtesting/efficient_trend_scalper.py`: optimized causal adapter. It precomputes indicators and uses positional timestamp lookup; one-day eight-candidate runtime decreased from about 28 seconds to about 13 seconds with identical results.
- `src/mt5_scalping_agent/strategies/trend_scalper.py`: existing M1/M5 trend strategy and small fixed variants.

## Historical data inventory
All data are EURUSD bid-side M1 OHLCV with normalized UTC timestamps and strict OHLCV validation.

- `data/histdata/`: HistData Generic ASCII archive, fixed EST normalized to UTC.
  - Years 2003-2018 are present (16 annual files).
  - 2019 HistData was rejected, not silently repaired, because it contained duplicate timestamps with differing prices around the DST period.
- `data/dukascopy_annual/`: Dukascopy public bid-side M1 archive.
  - Years 2019-2026 are present (8 annual files).
  - 2019-2025 contains 2,606,275 bars.
  - 2026 is year-to-date and currently ends at `2026-08-21T20:59:00Z`.
- Do not treat 2003-2026 as a uniform single-provider series. The loader deliberately rejects any range that crosses `2019-01-01`; run HistData and Dukascopy periods separately.
- Key manifests:
  - `data/histdata/EURUSD_m1_2003_2005_manifest.json`
  - `data/dukascopy_annual/EURUSD_m1_2019_2019_manifest.json`
  - `data/dukascopy_annual/EURUSD_m1_2020_2025_manifest.json`
  - `data/dukascopy_annual/EURUSD_m1_2026_2026_manifest.json`

## Experiment runner and reports
- `scripts/run_experiments.py` now defaults to the local archive; use `--data-source mt5` only for explicit MT5 historical loading.
- It accepts `--experiments` to run selected fixed candidates.
- Reports now preserve legacy fields while adding lots, gross PnL, spread/slippage/commission decomposition, net expectancy, payoff, holding duration, MAE/MFE, break-even costs, and rejection reasons.
- Research runners write sidecar manifests that freeze strategy implementation/parameters, exact periods, dataset and code hashes, costs, equity, risk limits, symbol settings, and deterministic seeds. A legacy, tampered, or incompatible checkpoint is refused unless `--restart` is explicit.
- `scripts/run_continuous_evaluation.py` cannot load 2024+ data. Its `research_diagnostics` profile makes loss/rate circuit breakers nonbinding while retaining sizing, minimum volume, stale data, spread, reward/risk, exposure, and single-position gates; `deployment_limits` preserves normal simulated circuit breakers.
- It also accepts `--tick-spread-csv` and `--tick-spread-statistic median|p95`. Only fresh tick records can override manual `--spread-points`; stale tick data is rejected.
- Local-archive assumptions used in reports: point/tick-size `0.00001`, tick value `1.0`, volume range `0.01-100`, 1.0 spread point, 0.5 slippage point, zero commission unless CLI options override them. These are research assumptions, not verified broker costs.

## Research results so far
The dated result sections below are retained as provenance. Any then-current "next step" is superseded by the current Verification, Recommended next steps, Resume point, and final diagnosis sections.

- Eight fixed variants were evaluated in the first full trading week of each year, 2019-2026, entirely in the Dukascopy segment.
- Aggregate report: `reports/research_windows/dukascopy_2019_2026_weekly_summary.json`.
- No candidate is stable or eligible for paper trading.
  - London morning: 3 profitable weeks of 8; total `-749.66`.
  - M1 pullback: 3/8; total `-841.44`.
  - Strict RSI: 1/8; total `-1669.62`.
  - Baseline: 1/8; total `-3038.52`.
- Structural diagnostics report: `reports/structural_diagnostics/dukascopy_2019_2026_structural_summary.json`.
  - London-morning buys: `-1205.04`; sells: `+455.38` across the full sample.
  - This is not a valid new short-only strategy: in chronological discovery 2019-2023, London sells were `-46.26`; only holdout 2024-2026 was positive (`+501.64`). Do not create a direction filter from this observation.
- Interpretation: the present M1/M5 trend family is regime-unstable. Do not parameter-tune it further or promote it.

## Broker tick/spread calibration
- `src/mt5_scalping_agent/data/tick_capture.py`: read-only recorder validates bid/ask and writes UTC ticks with computed spread points.
- `scripts/capture_mt5_ticks.py`: capture CLI. No execution capability.
- `src/mt5_scalping_agent/data/tick_analysis.py` and `scripts/analyze_mt5_ticks.py`: freshness checks plus min/median/p95/max spread statistics.
- Sunday-opening, London, and New York read-only captures are complete. The RoboForex ECN New York file contains 3,600 observations, 3,313 fresh records, median spread 1 point, p95 2 points, and maximum 4 points.
- The broker-specific research model is spread 2 points, slippage 1 point, and USD 2 commission per standard lot per side. Captured files are one-second quote snapshots, not a historical event-tick replay or latency measurement.
- `docs/TICK_REPLAY_DESIGN.md` specifies the future tick source, bid/ask fills, ordering, gaps, stale/duplicate handling, latency, position transitions, and causal M1/M5 replay. It is design only; no execution or tick-replay engine was added.

## Verification
- Latest complete full suite: `295 passed`.
- Safety audit found no order APIs. `Settings.assert_order_submission_allowed()` always raises, the MT5 client is read-only, and the execution package has no implementation.
- The typed research registry contains exactly 16 strategies and all are `REJECTED`. The legacy generic backtesting registry remains at 14 because Strategies 15 and 16 require specialized research-only bindings.
- Strategy 15 and Strategy 16 base/stress development evaluations are complete. Every manifest is restricted to Dukascopy `[2019-01-01, 2024-01-01)`; no 2024-2026 data was loaded. No research or capture process is running.

## Recommended next steps
1. Review `reports/strategy16/eurusd_2019_2023_strategy16_development.json` and this handoff.
2. STOP. Do not tune or reinterpret Strategies 15 or 16, run their parameter neighborhoods, access 2024-2026 for either, create Strategy 17, or implement broker execution without a new explicit user authorization.
3. Preserve the Strategy 15 and Strategy 16 evidence records and frozen preregistration fingerprints in `config/research_registry.json`.

## Additional New York baselines (2026-08-22)
All results below use the same eight pre-specified first-full-trading-week EURUSD M1 windows (2019-2026) and provisional costs: 1.0 spread point, 0.5 slippage point, zero commission. They are research results only.

- `NewYorkReversalStrategy`: 734 trades; 7/8 positive windows; aggregate net `+3379.78`. This remains the leading New York-specific candidate.
- `NewYorkBollingerRsiReversalStrategy`: a fixed RSI(14) exhaustion confirmation added to the New York Bollinger reversal. 364 trades; 6/8 positive windows; aggregate net `+1840.86`. It did not improve on the unfiltered New York reversal.
- `NewYorkOpeningRangeBreakoutStrategy`: trades one 12:00-13:00 UTC opening-range break, aligned with the 20-bar mean. 37 trades; 3/8 positive windows; aggregate net `+90.54`. It is weak and unstable; do not prioritize it.
- New source files: `src/mt5_scalping_agent/backtesting/new_york_opening_range.py` and tests in `tests/backtesting/test_new_york_opening_range.py`.
- Reports: `reports/classic_baselines/*_new_york_bollinger_rsi_reversal.json` and `reports/classic_baselines/*_new_york_opening_range_breakout.json`.

The priority comparison group remains plain Bollinger mean reversion, New York reversal, and London range breakout. Re-run them on longer fixed windows after London and New York broker-cost captures are available.
## Additional baseline results (2026-08-22, second batch)
These three fixed-rule baselines used the same eight pre-specified first-full-trading-week EURUSD M1 windows (2019-2026) and provisional costs: 1.0 spread point, 0.5 slippage point, zero commission. They are not optimized results and remain research-only.

- `DoubleBollingerBreakoutStrategy`: 1,597 trades; 0/8 positive windows; aggregate net `-4618.59`. Rejected.
- `RsiTrendBreakoutStrategy`: 200 trades; 3/8 positive windows; aggregate net `-1024.93`. Rejected.
- `AtrFilteredMeanReversionStrategy`: fixed Bollinger mean reversion with ATR(14) no more than twice the preceding 20-bar median true range. 2,800 trades; 8/8 positive windows; aggregate net `+4961.96`. Promising, but it must be tested on longer fixed windows and with captured broker costs before any promotion.

The candidate comparison group is now plain Bollinger mean reversion, ATR-filtered mean reversion, New York reversal, and London range breakout. The next research stage is not more parameter tuning: it is chronological development/holdout validation with representative London and New York transaction costs.
## Online-strategy screening batch (2026-08-22)
The project does not treat marketplace claims as evidence. Public strategies are only admitted when their entry, stop, target, session, and position-limit rules can be specified and simulated causally. Grid, martingale, averaging-down, discretionary, proprietary, and insufficiently specified systems are excluded.

- `NewYorkOpeningRangeRetestStrategy`: a 12:00-12:30 UTC range break, retest, then re-break with a 20-bar trend check. 36 trades; 5/8 positive windows; aggregate net `-18.94`. Flat and too sparse. Rejected.
- `PreviousDayRangeBreakoutStrategy`: one intraday break of the completed prior UTC day's range. 12 trades; 4/8 positive windows; aggregate net `+123.36`. Too few trades and insufficient evidence. Do not prioritize.
- New code: `src/mt5_scalping_agent/backtesting/online_baselines.py`; tests: `tests/backtesting/test_online_baselines.py`.
- The runner now uses an explicit `STRATEGIES` registry in `scripts/run_london_range_breakout.py`, making future baseline additions clearer and safer.
- Latest verification: `95 passed`.
## Fixed chronological robustness validation (2026-08-22)
- Runner: `scripts/run_chronological_validation.py`.
- Rule: first Monday of each calendar year, then a fixed consecutive 28-day EURUSD M1 window. Development: 2019-2023 (five windows). Post-selection holdout: 2024-2026 (three windows). The report is `reports/chronological_validation/eurusd_2019_2026_four_week_summary.json`.
- This is a chronological robustness check, not a blind holdout, because prior screening reviewed a one-week sample from 2024-2026. It used the same provisional costs: 1.0 spread point, 0.5 slippage point, zero commission.

| Strategy | Development: trades / net / positive windows | Post-selection: trades / net / positive windows | Interpretation |
| --- | --- | --- | --- |
| Bollinger mean reversion | 7,789 / `+13625.77` / 4 of 5 | 3,355 / `+645.59` / 1 of 3 | Severe deterioration; not promoted. |
| ATR-filtered mean reversion | 7,652 / `+11146.87` / 4 of 5 | 3,381 / `+560.18` / 1 of 3 | Severe deterioration; not promoted. |
| New York reversal | 1,972 / `+7079.18` / 4 of 5 | 1,091 / `+924.24` / 2 of 3 | Leading research candidate, but still requires calibrated costs and broader robustness tests. |
| London range breakout | 72 / `+577.81` / 2 of 5 | 42 / `-293.55` / 0 of 3 | Rejected. |

No strategy is approved for paper trading or live trading. The next validation action is re-running the surviving mean-reversion and New York candidates with fresh, session-specific broker spreads/slippage after scheduled tick captures complete.
## All-strategy chronological comparison (2026-08-22)
- `scripts/run_chronological_validation.py` now evaluates all 13 fixed-rule baselines through `backtesting/strategy_registry.py`, including rejected strategies. Rules and provisional costs were unchanged.
- Full report: `reports/chronological_validation/eurusd_2019_2026_all_strategies_four_week_summary.json`.
- Development/post-selection net results: London `+577.81` / `-293.55`; Bollinger `+13625.77` / `+645.59`; Donchian `-4147.56` / `+426.71`; MA crossover `-4380.86` / `-2257.05`; range filter `-4231.59` / `-2502.52`; New York reversal `+7079.18` / `+924.24`; New York Bollinger-RSI reversal `+5339.10` / `+2181.00`; New York ORB `-765.98` / `-435.79`; double Bollinger `-4400.36` / `-1590.77`; RSI trend breakout `-2979.78` / `-496.16`; ATR-filtered mean reversion `+11146.87` / `+560.18`; New York retest `-794.25` / `-375.14`; prior-day range breakout `+118.31` / `+67.12`.
- The leading post-selection research candidate is now New York Bollinger-RSI reversal (2 of 3 positive windows), followed by New York reversal (2 of 3). This remains provisional and is not a paper-trading approval.
## Four-month all-strategy validation completed (2026-08-23)
- Final report: `reports/chronological_validation/eurusd_2019_2026_all_strategies_four_month_summary.json`.
- Coverage: January, April, July, and October fixed 28-day windows; 2019-2025 have four windows each, 2026 has January/April/July only. October 2026 was correctly skipped as unavailable.
- Total: 31 windows and 403 strategy-window results. Rules were unchanged. Costs remain provisional: 1.0 spread point, 0.5 slippage point, zero commission.
- New York Bollinger-RSI reversal is the clear leader: development `+4921.36` (10/20 positive), post-selection `+3943.08` (7/11 positive), combined `+8864.44` with 5,759 trades.
- Plain New York reversal ranks second: development `+5962.59` (11/20), post-selection `+672.68` (6/11), combined `+6635.27` with 10,240 trades. Its later edge is much weaker.
- Broad Bollinger mean reversion nearly disappears post-selection: development `+6407.25`, post-selection `+43.41`.
- ATR-filtered mean reversion reverses from development `+2990.59` to post-selection `-2523.84`; reject for promotion.
- Previous-day range breakout is positive in 18/31 windows but has only 103 trades and `+201.64` combined; evidence is too sparse.
- London breakout and all remaining trend/breakout baselines are rejected.
- No strategy is approved for paper or live trading. Next required step is broker-cost calibration and cost-sensitive reruns of New York Bollinger-RSI reversal and plain New York reversal.
## Sunday broker-opening tick capture (2026-08-23)
- Scheduled task completed successfully with result `0`: 3,600 new EURUSD observations from 22:30-23:30 Europe/London.
- Broker MT5 tick timestamps are UTC+3 relative to local UTC observations. `analyze_mt5_ticks.py` now accepts explicit `--broker-time-offset-hours` and bounded `--maximum-clock-skew-seconds`; defaults remain strict.
- Analysis used `--broker-time-offset-hours 3 --maximum-clock-skew-seconds 1` and found 2,221 fresh records of 3,602 total rows. Repeated quotes older than five seconds and the two prior stale rows account for 1,381 stale records.
- Fresh opening-session spreads: median `1.0` point, p95 `8.0` points, maximum `10.0` points. All fresh records are classified `off_session`, so `recommended_conservative_spread_points` correctly remains null.
- Do not use this Sunday-opening sample to calibrate New York strategies. At that stage the London and New York captures remained required; both were subsequently completed as documented below.
- Latest verification: `99 passed`.
## London broker tick capture (2026-08-24)
- Scheduled 08:00 Europe/London capture completed successfully: 3,600 observations and task result `0`.
- Tick parsing now accepts valid mixed ISO timestamp precision (`format="mixed"`); seven whole-second broker timestamps had exposed pandas format inference. Verification is now `100 passed`.
- Combined analysis used explicit broker offset `+3 hours` and maximum clock skew `1 second`.
- Fresh London records: 3,583. Spread points: median `0.0`, p95 `1.0`, maximum `2.0`. Conservative London recommendation: `1.0` point.
- Zero-point quotes are present in the broker feed and should not be generalized to execution costs. Commission and slippage are still separate assumptions.
- Do not substitute London spread calibration for the New York candidates; wait for the scheduled 13:00 New York capture.
## New York broker tick capture completed (2026-08-24)
- The scheduled task stopped after 1,839 samples; a communicated recovery capture appended the remaining 1,761. Final New York sample count: 3,600. Recovery errors: none.
- Combined normalized analysis: 10,802 total CSV rows, 9,381 fresh records. Broker time offset `+3 hours`, maximum clock skew `1 second`.
- Fresh New York records: 3,577. Spread points: median `0.0`, p95 `1.0`, maximum `1.0`.
- Fresh London records remain 3,583: median `0.0`, p95 `1.0`, maximum `2.0`. Conservative normal-session spread recommendation: `1.0` point.
- The completed 31-window strategy validation already used spread `1.0` point and slippage `0.5` point, so a rerun with the measured p95 spread alone would be identical. Broker commission remains unverified.
- Next useful validation is cost sensitivity for New York Bollinger-RSI reversal and plain New York reversal under higher spread/slippage assumptions, rather than duplicating the baseline run.
## Cost sensitivity completion (2026-08-24)

The two fixed New York candidates were rerun over all 31 available January/April/July/October windows without changing their strategy rules.

- Baseline (spread 1 point, slippage 0.5 point, commission 0): `new_york_reversal` dev +5962.59 / post +672.68; `new_york_bollinger_rsi_reversal` dev +4921.36 / post +3943.08.
- Moderate (spread 2 points, slippage 1 point, commission 0): `new_york_reversal` dev -3096.46 / post -3654.09; `new_york_bollinger_rsi_reversal` dev -458.33 / post -274.51.
- Severe (spread 5 points, slippage 2 points, commission 0): both strategies placed zero trades in every window because the existing cost gate rejected all entries.
- Severe report: `reports/chronological_validation/new_york_candidates_severe_cost.json`.

Conclusion: neither candidate is approved for live or demo-forward trading yet. The Bollinger-RSI candidate is the stronger research lead, but its historical edge is too small to survive the moderate friction scenario.

The connected terminal identifies itself as `MetaQuotes Ltd. / MetaQuotes-Demo` (`trade_allowed=False`). It is not a real broker account and therefore cannot supply a deployable commission schedule. Before further cost validation, connect the intended broker demo/live account and obtain its exact EURUSD account type, commission per lot per side (or round turn), and typical session spreads. Continue to keep execution disabled.
## RoboForex ECN broker-specific validation (2026-08-24)

The terminal was verified as `RoboForex Ltd / RoboForex-ECN`, demo mode, with `trade_allowed=False` and symbol `EURUSD`. A read-only New York capture completed 3,600 samples: 3,313 fresh, median spread 1 point, p95 2 points, and maximum 4 points. RoboForex's published ECN EURUSD commission is `20 / mio`, modeled as USD 2 per standard lot per side.

The two unchanged New York candidates were rerun across all 31 available fixed January/April/July/October windows using spread 2 points, slippage 1 point, and commission USD 2 per lot per side:

- `new_york_reversal`: development -15,256.24 (3,337 trades, 2/20 positive windows); post-selection -9,574.99 (1,985 trades, 0/11 positive windows); combined -24,831.23.
- `new_york_bollinger_rsi_reversal`: development -10,117.11 (2,951 trades, 3/20 positive windows); post-selection -6,126.64 (1,672 trades, 3/11 positive windows); combined -16,243.75.

Report: `reports/chronological_validation/new_york_candidates_roboforex_ecn_cost.json`.

Decision: reject both candidates for deployment in their current form. Do not tune their parameters against the reviewed 2024-2026 windows. The next research phase should reduce turnover structurally and validate a genuinely new candidate chronologically under broker-specific costs before any forward-trading phase.
## Lower-turnover development screen and current handoff state (2026-08-24)

A new fixed-rule candidate, `new_york_bollinger_reentry`, was added as a structural response to commission sensitivity. It is not a retuning of either rejected New York strategy. Rules: New York UTC session only; prior close outside a 20-bar two-standard-deviation Bollinger band; current close back inside the recalculated band; RSI(14) exhaustion at 30/70; ATR(14) stop; fixed 2R target; at most one emitted trade per UTC day.

- Implementation: `src/mt5_scalping_agent/backtesting/new_york_reentry.py`.
- Registry: `src/mt5_scalping_agent/backtesting/strategy_registry.py` now contains 14 strategies.
- Tests: `tests/backtesting/test_new_york_reentry.py`; full verification is `103 passed`.
- Development-only report: `reports/chronological_validation/new_york_bollinger_reentry_roboforex_development.json`.
- Coverage: 20 fixed January/April/July/October 28-day windows from 2019-2023 only.
- Costs: spread 2 points, slippage 1 point, commission USD 2 per lot per side.
- Result: 321 trades, net `-1215.12`, 6/20 positive windows, worst window `-371.50`.

Decision: reject this candidate at development screening. The one-trade-per-day rule reduced turnover substantially, but the signal remained unprofitable after broker-specific costs. Do not run this candidate on 2024-2026 and do not tune it against that reviewed period.

### Resume point for the next AI

- No research backtest or capture process is running. The corrected risk-sized and constant-exposure diagnostics and assessments are complete.
- MT5 is connected to `RoboForex Ltd / RoboForex-ECN` demo; automated trading is disabled (`trade_allowed=False`). Never enable execution during research.
- No strategy is approved for demo-forward or live trading. The typed research registry contains exactly 16 strategies and preserves all `REJECTED` decisions.
- Phases 1-8, Phase A signal economics, Phase B economic requirements, and the prospectively frozen Strategy 15 and 16 development evaluations are complete. Current verification is `295 passed`.
- Strategies 15 and 16 are implemented and rejected. Do not retune either, create Strategy 17, implement order submission, or use 2024-2026 for parameter selection.
- The constant-exposure run is recorded against the two existing rejected registry entries as `constant_exposure_signal_economics_v1`. Review `docs/STRATEGY_15_RESEARCH_BRIEF.md`, then STOP; do not start another experiment or propose a strategy.

## Research infrastructure and final diagnosis (2026-08-24)

- Phases 1-8 are complete: explicit trade economics, deterministic manifests/checkpoints, archive quality and DST-aware session utilities, split-isolated continuous evaluation, 14-strategy research registry, deterministic robustness statistics, reusable simulated risk state, and tick-replay design.
- Archive audit: 24 accepted annual files and 8,424,015 observed M1 rows. It classified 484,324 absent expected-active minutes as 240,120 short possible no-tick gaps and 244,204 unexplained gaps. It found no duplicate, malformed, off-grid, OHLC-invalid, or invalid-volume rows; zero-volume semantics are reported separately. Longest expected-active gap: 5,281 minutes in HistData 2003.
- Final continuous report: `reports/continuous_evaluation/eurusd_2019_2023_new_york_leaders_research_diagnostics.json`.
- Deterministic assessment: matching `_assessment.json` and `_assessment.md` files. Run ID: `continuous_development_evaluation:7acb480aaad215a4`.
- Scope is strictly `[2019-01-01, 2024-01-01)`. Costs are RoboForex ECN assumptions: 2 spread points, 1 slippage point, and USD 2/lot/side commission. Strategy rules were unchanged; 2024-2026 was not loaded.

| Strategy | Trades | Gross | Spread | Slippage | Commission | Total costs | Net | Gross/trade | Cost/trade |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| New York Bollinger-RSI reversal | 7,512 | `+6321.51` | `4656.48` | `2328.24` | `9312.96` | `16297.68` | `-9976.17` | `0.8415` | `2.1696` |
| New York reversal | 5,144 | `+5491.96` | `4422.76` | `2211.38` | `8845.52` | `15479.66` | `-9987.70` | `1.0676` | `3.0093` |

- Bootstrap 95% gross-expectancy intervals are positive for both: Bollinger-RSI `[0.3920, 1.2742]`; plain reversal `[0.5115, 1.5890]`. Net intervals are entirely negative: Bollinger-RSI `[-1.7550, -0.8985]`; plain reversal `[-2.4937, -1.4486]`.
- Break-even all-in costs are only `0.8415` and `1.0676` per trade. Break-even spread is undefined for both because slippage plus commission alone already exceeds gross edge.
- Neither strategy had a positive year. Positive active months were 6/56 for Bollinger-RSI and 4/46 for plain reversal. Net-positive profit is concentrated: the top 10% of trades contribute 87.2% and 78.3% of the respective positive-profit pools.
- Dominant failure mechanism: `TRANSACTION_COSTS`. Temporal instability also contributes. Losses then reduce equity below broker minimum sizing, causing 10,462 Bollinger-RSI and 33,718 plain-reversal intent rejections; later-year results therefore measure portfolio survival, not constant-notional signal quality.
- The result remains an M1 candle simulation with fixed costs and IID bootstrap diagnostics, not tick replay, variable spread, latency, or execution evidence. Both strategies remain `REJECTED`; no strategy is approved for demo or live deployment.
- An earlier incomplete `eurusd_2019_2023_new_york_leaders.checkpoint.json` used deployment-style circuit breakers and was intentionally stopped after persistent drawdown censorship was identified. Do not treat it as the final diagnostic.

## Constant-exposure diagnosis and Strategy 15 brief (2026-08-24)

- Final report: `reports/signal_economics/eurusd_2019_2023_new_york_leaders_fixed_1lot.json`; run ID `constant_exposure_signal_economics:46effe3c7bd8a796`.
- Human assessment: matching `_assessment.md`; detailed ledgers are in the matching `_details/` directory. Both ledger SHA-256 fingerprints match the report.
- The manifest contains only EURUSD M1 files for 2019, 2020, 2021, 2022, and 2023. Post-selection access is explicitly false.
- `new_york_bollinger_rsi_reversal`: 13,846 fixed-1-lot signals; gross `+0.2833 pip/signal`; cost `0.7000`; net `-0.4167`; total net `-57,696.30`; 0/5 positive years and 8/60 positive months.
- `new_york_reversal`: 25,148 fixed-1-lot signals; gross `+0.2218 pip/signal`; cost `0.7000`; net `-0.4782`; total net `-120,269.94`; 0/5 positive years and 3/60 positive months.
- Median MFE/MAE was `3.1/3.0 pips` and `2.5/2.5 pips`; gross expectancy captured only 5.9% and 5.5% of mean MFE. Every direction, causal volatility regime, and DST-aware New York local-hour subsection remained net-negative.
- Gross expectancy declined descriptively from first to second half (`0.3261` to `0.2411`, and `0.2423` to `0.2018 pip/signal`) independent of balance.
- Conclusion: portfolio depletion previously censored further losses; it did not hide viability. Both paths remain permanently `REJECTED` and are closed to tuning or variation.
- `docs/STRATEGY_15_RESEARCH_BRIEF.md` freezes the economic problem, base/stress cost models, approximate required edge/movement/frequency/holding/stop/reward profile, and future promotion evidence requirements. It does not define or implement Strategy 15.
## Strategy 15 frozen development result (2026-08-30)

- Hypothesis: after an objectively measured M5 compression, a strong New York-session expansion aligned with completed M15 directional context may continue after a shallow retest and confirmed re-break. The design deliberately sought larger movement, structural stops, and low turnover rather than another mean-reversion variation.
- Frozen implementation: `src/mt5_scalping_agent/backtesting/compression_expansion_continuation.py`. Governing specification: `docs/STRATEGY_15_RESEARCH_BRIEF.md`; registry research ID: `strategy_15_compression_expansion_controlled_continuation_v1`; preregistration fingerprint: `sha256:ea560ec22b835bd1010602ca419843c584adde33b73b9cb433984cc0b5249ff6`.
- Development scope was exactly Dukascopy EURUSD M1 `[2019-01-01, 2024-01-01)`. The runner rejects any other period/provider before archive access. Position sizing was fixed at 1.0 lot and rules were unchanged between cost scenarios.
- Base costs: spread 2 points, slippage 1 point, commission USD 2/lot/side. Stress costs: spread 4 points, slippage 2 points, commission USD 2/lot/side.
- Both scenarios examined 53,896 potential expansion bars but produced 0 eligible setups, 0 emitted signals, 0 accepted trades, and 0 rejected intents. Therefore PnL and costs were zero, while expectancy, profit factor, holding, MFE, and MAE were undefined rather than treated as evidence of break-even performance.
- Dominant frozen-rule exclusions in each scenario: compression threshold 52,155; expansion threshold 905; incomplete/nonconsecutive M5 context 599; compression box width 491; nondirectional M15 context 332; deep retest invalidation 6; target touched before entry 3; missing confirmation 3; missing retest 1.
- Primary decision: `FAIL`. Nineteen primary gates failed, including frequency (required 250-500 signals in every year), gross/base/stress expectancy, MFE, MFE/MAE, cost/MFE, holding evidence, stop/reward evidence, profit factor, positive years, and positive active months. Maximum entries/day and no-overnight checks passed vacuously.
- Block bootstrap, effective sample size, downside-tail, concentration, risk-sized drawdown, and frozen parameter-neighborhood checks were `NOT_EVALUATED` because primary gates failed. No attempt was made to rescue or tune the rules.
- Final report: `reports/strategy15/eurusd_2019_2023_strategy15_development.json`. Scenario evidence: matching `_details/base.json` and `_details/stress.json`; deterministic manifest and checkpoint are alongside the report.
- Registry status: `REJECTED / REJECTED`, with separate validated base and stress evidence records. No 2024-2026 data was accessed, no robustness run was eligible, and no broker execution was added.
## Strategy 16 frozen development result (2026-08-30)

- Hypothesis: an unusually large, directionally efficient EURUSD displacement in the fixed 08:30 America/New_York U.S. macro-release window that retains its direction during 08:35-08:39 may continue after 08:40 as price discovery and risk transfer complete. This was a scheduled-news-clock hypothesis, distinct from the prior generic breakout, reversal, opening-range, and compression-expansion families.
- Governing brief: `docs/STRATEGY_16_RESEARCH_BRIEF.md`. Implementation: `src/mt5_scalping_agent/backtesting/scheduled_macro_shock.py`. Registry research ID: `strategy_16_scheduled_us_macro_shock_continuation_v1`; immutable preregistration fingerprint: `sha256:758806be23c4388df121bf0ddc2f7465b6e31375a61a735f6c9eb7d3654ff606`.
- Scope: accepted Dukascopy EURUSD M1 only in `[2019-01-01, 2024-01-01)`. The runner rejects any other period/provider before archive access. No 2024-2026 data was loaded.
- Frozen rules: 60-minute 07:30-08:29 New York baseline; 08:30-08:34 abnormal, efficient shock; 08:35-08:39 retained/reaccelerating stabilization; exact 08:40 next-M1 entry; one intent per New York date; 5-15 pip structural stop; 2.25R target; 80-minute hard exit; no overnight or position management changes.
- Costs: base spread/slippage/commission were 4 points/2 points/USD 2 per lot per side, approximately 1.0 pip all-in. Stress was 10 points/5 points/USD 2 per side, approximately 1.9 pips all-in. These are conservative fixed research costs, not historical news-tick execution evidence.
- Both base and stress evaluated 1,298 weekday event-clock dates and emitted/accepted 21 trades. Annual counts were 3, 2, 6, 2, and 8, below the frozen 40-180 range for every year. Dominant exclusions: insufficient shock displacement 1,009; directional efficiency 104; abnormal-range filter 55; reacceleration 46; maximum stop 18; retracement 18; intrastabilization retention 12.
- Base: gross `+244.88` USD (`+1.1661` pips/trade), transaction costs `210.00`, net `+34.88` (`+0.1661` pips/trade), PF `1.0276`, median MFE `8.4` pips, median adverse MAE `8.4` pips, median hold 35 minutes, maximum drawdown `511.62` USD.
- Stress: gross `+357.37` USD, transaction costs `399.00`, net `-41.63` (`-0.1982` pips/trade), PF `0.9693`. Differences in gross reflect the strategy’s actual-entry economics at higher simulated friction; the rules were unchanged.
- Primary decision: `FAIL`. Ten primary gates failed: gross/base/stress expectancy, MFE exceedance, MFE/MAE, annual signal frequency, base/stress PF, positive years, and positive active months. MFE level, cost/MFE, entry limit, holding duration, hard exit, no overnight, and structural risk/reward gates passed.
- Block bootstrap, effective sample size, downside-tail, concentration, risk-sized drawdown, and frozen neighborhood checks were `NOT_EVALUATED` because the primary gates failed. No rules were relaxed and no rescue run was performed.
- Final report: `reports/strategy16/eurusd_2019_2023_strategy16_development.json`; base/stress evidence is in the matching `_details/` directory with manifest and checkpoint alongside it. Registry status is `REJECTED / REJECTED` with two validated evidence records. No DEMO/LIVE functionality was added and Strategy 17 was not created.
## Cross-pair feasibility pilot (2026-08-31)

- This is a data and broker-cost feasibility phase, not a strategy result or a claim that EURUSD is intrinsically unprofitable. The established result is that the reviewed EURUSD M1 candidates did not survive RoboForex ECN costs.
- `GBPUSD` and `USDJPY` 2019 Dukascopy bid-side M1 pilot archives were downloaded, gzip-verified, and recorded in `reports/cross_pair_feasibility/dukascopy_2019_pilot.json`.
  - GBPUSD: 373,119 bars, median M1 range 1.4 pips.
  - USDJPY: 372,881 bars, median M1 range 0.9 pips using the correct 0.01 pip convention.
- `USDCAD` was added to the explicit Dukascopy instrument map but its 2019 annual request was interrupted before completion. It failed gzip integrity and both the corrupt file and manifest were removed. It is not eligible for research until a complete archive is obtained.
- Annual Dukascopy downloader writes are now atomic, so an interrupted future annual import cannot leave a file that is mistaken for validated research data.
- No GBPUSD, USDJPY, or USDCAD strategy has been run. Broker-specific point/tick value, commission, and London/New York spread captures must be obtained for each pair before a fixed cross-pair strategy comparison. Strategy 17 remains unevaluated and no post-selection data has been accessed.
## Cross-pair broker feasibility update (2026-08-31)

- Read-only MT5 symbol checks confirmed `GBPUSD` and `USDJPY` on RoboForex-ECN demo. GBPUSD point/tick size/value are `0.00001`/`0.00001`/USD `1.0` per lot-tick. USDJPY point/tick size are `0.001`/`0.001`, its pip is `0.01`, and the terminal reported USD `0.6263937260` per lot-tick at the sampled price. Do not reuse EURUSD economics for USDJPY.
- Short London quote pilots captured 30 records per pair and used UTC+3 broker-time normalization. GBPUSD had 16 fresh records, 2-point median/p95 spread; USDJPY had 30 fresh records, 2-point median and 3-point p95 spread. These samples are feasibility-only and not calibrated strategy costs.
- RoboForex's current official ECN contract pages list `20 / mio` commission for GBPUSD and USDJPY, 0.0001/0.01 pip sizes, and 0.00001/0.001 tick sizes respectively. Account-currency commission conversion and session variation must be modeled separately.
- Report: `reports/cross_pair_feasibility/roboforex_ecn_symbol_and_london_pilot.json`. Required next evidence is longer fresh London and New York samples for each pair, then complete validated 2019-2023 data for only the retained pairs. No cross-pair strategy run is authorized by these pilots.
## Cross-pair capture scheduling and archive status (2026-08-31)

- One-time interactive-user tasks are registered for 13:00 Europe/London today: `MT5 GBPUSD New York Tick Capture` and `MT5 USDJPY New York Tick Capture`. Each runs the existing read-only capture script for 3,600 one-second observations into `data/mt5_ticks/roboforex_ecn_cross_pair/`. They do not and cannot submit orders.
- The 2020 GBPUSD annual request did not finish before the command window ended. The corrected atomic downloader left no partial archive or manifest, so no 2020 GBPUSD file is eligible for use. Do not retry this as a one-shot annual download; implement a resumable chunk importer before requesting the remaining 2019-2023 cross-pair archive files.
- Current usable cross-pair archive evidence remains the gzip-verified 2019 GBPUSD and USDJPY pilots only.
## Resumable cross-pair archive importer (2026-08-31)

- New script: `scripts/import_dukascopy_annual_resumable.py`. It fetches no more than a caller-selected number of 14-day chunks per invocation, validates each chunk before writing it atomically, revalidates existing chunks on resume, and creates an annual archive only after every chunk completes.
- Verification: focused importer/downloader/symbol tests `7 passed`.
- GBPUSD 2020 is complete: 374,189 validated M1 bars in `data/dukascopy_annual/GBPUSD_m1_2020.csv.gz`.
- GBPUSD 2021 is complete: 371,580 validated M1 bars in `data/dukascopy_annual/GBPUSD_m1_2021.csv.gz`.
- GBPUSD 2022 has its first 8 of 27 validated chunks stored under `data/dukascopy_annual/chunks/GBPUSD/2022/`; the annual file has correctly not been created yet. Resume with the same command and `--max-chunks 8`.
- No cross-pair strategy evaluation has used these files. GBPUSD 2019-2023 and USDJPY 2019-2023 completion, plus the scheduled longer broker captures, remain prerequisites.
## Autonomous research operating contract (authorized 2026-08-31)

- Routine research work may continue without repeated user prompts: read-only data ingestion, archive validation, scheduled read-only quote capture, data-quality checks, fixed-rule evaluation, tests, reports, and handoff updates.
- Hard stops remain: never enable or implement broker execution; never promote a candidate, access 2024-2026 for selection, tune a rejected/frozen rule, materially alter a frozen gate, create a new strategy, or add a paid/external provider without explicit user review.
- Every substantial operation must retain an atomic checkpoint or manifest where the project already supports one. Communicate decisions, failures, and externally scheduled activity; do not represent a scheduled task as completed until its artifacts are verified.
## Cross-pair archive progress (2026-08-31)

- GBPUSD 2019-2023 development archive is complete and validated: 2019 pilot plus 2020 (374,189 bars), 2021 (371,580), 2022 (372,627), and 2023 (371,939). Every annual file was assembled only after validated resumable chunks completed.
- USDJPY 2019 pilot is complete. USDJPY 2020 has its first 8 resumable chunks stored; no annual 2020 file exists until the remaining chunks validate and assemble.
- The cross-pair work remains data/cost preparation only. No Strategy 17 evaluation or any cross-pair strategy test has been run, and no post-selection data was accessed.
## USDCAD added to the cross-pair feasibility universe (2026-08-31)

- Read-only RoboForex MT5 check confirmed USDCAD: point/tick size `0.00001`, terminal USD tick value `0.7195538766` per lot-tick at the sampled price, and current 3-point quote spread. It requires pair-specific economics.
- `MT5 USDCAD New York Tick Capture` is registered as a one-time interactive-user, read-only 3,600-observation task for 13:00 Europe/London today.
- USDCAD 2019 is complete via the resumable importer: 373,148 validated M1 bars at `data/dukascopy_annual/USDCAD_m1_2019.csv.gz`. The prior corrupt one-shot file was never retained.
- The comparison universe is GBPUSD, USDJPY, and USDCAD. Each remains data/cost preparation only until its full 2019-2023 archive and broker-cost captures are complete.
## Strategy 17 pre-evaluation correction (2026-08-31)

- The initial Strategy 17 `PROPOSED` record omitted five runtime cost/economics defaults. No implementation lifecycle transition, archive load, backtest, report, or experiment evidence had occurred.
- After explicit user authorization, `scripts/correct_strategy17_preregistration.py` added only those missing defaults, updated provenance with the amendment reason, and produced the new frozen fingerprint `sha256:41850803b46be1f9eec948ee2a1184f346933b1570db244f77863f65e90e522e`.
- `scripts/run_strategy17_development.py` is bound to that fingerprint and will refuse drift before archive access. Strategy 17 remains `PROPOSED` and unevaluated. Focused registry/strategy tests: `21 passed`.
- USDJPY 2020 now has 16 of its resumable chunks complete; its annual archive will not be created until all chunks validate.
## Cross-pair archive checkpoint (2026-08-31, 10:32 Europe/London)

- USDJPY 2019-2023 development archive is now complete and validated: 2019 pilot plus 2020 (373,324 bars), 2021 (370,558), 2022 (372,729), and 2023 (372,029). No USDJPY strategy evaluation has been run.
- USDCAD 2019-2020 is now complete and validated: 2019 (373,148 bars) and 2020 (373,418). USDCAD 2021-2023 remains pending acquisition through the resumable importer.
- The focused importer suite now has explicit empty-market-chunk coverage: `2 passed`. This is necessary for valid holiday/weekend terminal chunks and does not change strategy behavior.
- The three one-time, interactive-user, read-only New York capture tasks for GBPUSD, USDJPY, and USDCAD remain scheduled for 13:00 Europe/London today. At 10:22 Europe/London none had run; do not claim capture results until their CSV artifacts and task results are checked.
- No long-running process is active. Next bounded unit: verify/analysis of the 13:00 captures, then resume USDCAD 2021-2023 archive acquisition and implement the generic pair-aware evaluation runner before any frozen strategy is transitioned to development.
## Multi-pair development readiness (2026-08-31, 10:43 Europe/London)

- The comparison universe now has complete validated Dukascopy M1 development archives for exactly `[2019-01-01, 2024-01-01)`: GBPUSD (2019-2023), USDJPY (2019-2023; 373,324 / 370,558 / 372,729 / 372,029 bars for 2020-2023), and USDCAD (2019-2023; 373,148 / 373,418 / 370,583 / 371,414 / 369,468 bars).
- New module: `src/mt5_scalping_agent/research/cross_pair.py`. `CrossPairDevelopmentSpec` accepts only GBPUSD, USDJPY, and USDCAD, enforces the common five-year development range and annual-file completeness, uses the correct USDJPY 0.01-pip convention, and refuses a mismatched or omitted pair-specific `SymbolRiskSpec`. It supplies no strategy, cost model, broker connection, or execution capability.
- New tests: `tests/research/test_cross_pair.py` (`5 passed`). It is a guardrail for the eventual generic evaluation runner, not a strategy comparison or a promotion decision.
- Remaining prerequisite before any frozen pair comparison: verify the scheduled 13:00 New York tick captures, analyze fresh records for each pair, and freeze pair-specific cost models from the capture plus commission conversion. Do not start Strategy 17 evaluation or transition its registry status until those costs and the generic runner are reviewed.
## Cross-pair New York calibration and cost-contract checkpoint (2026-08-31)

- The three one-hour, read-only New York tasks produced complete sample files. Fresh-record analysis used UTC+3 broker timestamp normalization, a five-second maximum tick age, and one-second maximum clock skew. Reports: `reports/cross_pair_feasibility/roboforex_ecn_GBPUSD_new_york_spread.json`, `..._USDJPY_...`, and `..._USDCAD_...`.
  - GBPUSD: 3,212 fresh New York records; spread median/p95/max `2/2/5` points; conservative measured spread `2` points.
  - USDJPY: 3,420 fresh New York records; spread median/p95/max `3/3/8` points; conservative measured spread `3` points.
  - USDCAD: 3,470 fresh New York records; spread median/p95/max `3/4/5` points; conservative measured spread `4` points.
- Task Scheduler reported `0x8007042B` after each task stopped, likely at the configured one-hour boundary. This is an operational defect for future scheduling, but it did not truncate these files: each contains the required 3,600 new observations (plus the prior 30-record pilots for GBPUSD/USDJPY).
- RoboForex ECN's published contract pages specify 0.0001/0.01 pip sizes, the observed tick increments, and `20 / mio` commission for GBPUSD, USDJPY, and USDCAD. The model must not convert that quote into a fixed USD-per-lot value without explicitly documenting notional and account-currency treatment, especially for GBPUSD and JPY/CAD-quoted pairs.
- New `CrossPairCostModel` requires separately stated spread, slippage, USD commission per lot per side, a local calibration report, and commission evidence. It computes round-trip cost in the pair's correct pip convention and refuses missing evidence. It does not include execution code or an assumed commission conversion.
- A fresh read-only account query confirmed `RoboForex Ltd / RoboForex-ECN`, USD account currency, login `67207777`. The broker account flags currently permit trade/expert activity, but this project still has no order API and its strict runtime BACKTEST gate continues to block submission. Never enable or add execution during this research phase.
- Do not transition Strategy 17 or evaluate any cross-pair strategy yet. Required next action: document the broker commission conversion method and fixed slippage assumptions per pair, then wire those explicit cost inputs into a generic evaluator for review.
## Frozen cross-pair costs ready for generic evaluation (2026-08-31)

- `config/cross_pair_cost_models.json` freezes base and stress research inputs before any cross-pair strategy evaluation. Base uses the measured New York p95 spread plus 1 point conservative slippage; stress uses the observed sample maximum spread plus 2 points slippage. Commission follows RoboForex's published ECN `20 / mio` schedule.
- GBPUSD uses USD `2.85` per lot per side: a conservative ceiling derived from one GBP 100,000-lot at the maximum observed isolated-development high of `1.42491`. USDJPY and USDCAD use USD `2.00` per lot per side because each standard lot is USD 100,000. This is an explicit, documented research approximation, not a historical fill replay.
- New read-only command: `scripts/audit_cross_pair_cost_models.py`. It uses the established `MT5ReadOnlyClient`, checks the current RoboForex ECN USD-account contracts, and writes `reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json`. It contains no order, position, or execution operation.
- Audited round-trip friction in pips: GBPUSD base/stress `0.87/1.27`; USDJPY `1.039424/1.639424`; USDCAD `1.055296/1.255296`. These values include spread, slippage, and two commission sides. USDJPY and USDCAD vary with the live USD tick value; the audit records the value used.
- The `CrossPairCostModel` and `load_frozen_cost_model` contracts reject missing calibration evidence, unsupported scenarios, malformed documents, and incorrect pip conventions. Focused tests: `8 passed`.
- Account-level MT5 flags currently report trade/expert permission at the broker, which is not an authorization to trade. Project code remains BACKTEST-only, `Settings.assert_order_submission_allowed()` still raises, and there is no order API. No strategy has been evaluated or advanced.
## Generic pair-aware evaluation runner (2026-08-31)

- `evaluate_pair_development` in `src/mt5_scalping_agent/research/cross_pair.py` is the reusable research-only adapter for a future pre-registered strategy. It requires a `CrossPairDevelopmentSpec`, an explicit frozen `CrossPairCostModel`, a strategy callback, risk limits, and fixed research volume.
- It loads exactly the isolated `[2019-01-01, 2024-01-01)` local archive through the existing completeness checks; creates the existing `BacktestConfig` with the selected pair costs; and delegates to `CandleBacktester`. It has no MT5 connection, no order method, no parameter selection, no post-selection access, and no strategy registry transition.
- Tests cover correct pip conventions, complete archive requirements, cost evidence requirements, frozen base/stress loading, invalid sizing rejection before archive access, and a synthetic end-to-end no-trade delegation. Focused: `10 passed`.
- The generic runner is now ready technically, but it is intentionally not invoked for Strategy 17: Strategy 17 remains frozen for EURUSD only and is still `PROPOSED`. Cross-pair evaluation requires a separately pre-registered and reviewed strategy specification; do not silently reuse or retune an EURUSD rule on another pair.
## Descriptive cross-pair session diagnostics (2026-08-31)

- New script: `scripts/run_cross_pair_session_diagnostics.py`. It loads the isolated 2019-2023 local M1 archives and reports DST-aware London-only, New-York-only, overlap, and other-session M1 range/body distributions relative to each pair's frozen base round-trip cost. It has no strategy, signal, backtest, MT5 connection, or broker action.
- Report: `reports/cross_pair_feasibility/cross_pair_session_movement_diagnostics.json`. GBPUSD base cost is `0.87` pips and p95 M1 ranges are 6.4 London-only / 7.5 New-York-only pips; USDJPY cost `1.039424`, ranges 4.8 / 6.3; USDCAD cost `1.055296`, ranges 4.1 / 6.4. The short civil-time overlap is a DST-transition artifact under the existing 08:00-13:00 local session definitions; it is not a separate tradable session conclusion.
- These are movement and friction descriptors, not expected returns, entry signals, or evidence of profitability. They must not be used to select a pair and then tune a strategy on the same 2019-2023 data. No Strategy 18 was created or evaluated from this diagnostic.
- Regression test `tests/test_cross_pair_session_diagnostics.py` verifies DST-aware London/New York/overlap labeling. Focused cross-pair and diagnostic tests: `11 passed`.
## Cross-pair preregistration governance (2026-08-31)

- The original research registry binds a strategy to one dataset and one cost model, so it cannot honestly preregister a three-pair candidate. New `src/mt5_scalping_agent/research/cross_pair_registry.py` supplies a separate strict registry for cross-pair proposals.
- A proposal must bind at least two unique pair records, each with an archive pattern and base/stress cost scenario; it must include frozen rules, parameters, and the complete existing frozen-strategy specification. New proposals are accepted only as `PROPOSED`, with no implementation and no experiment evidence.
- Empty registry: `config/cross_pair_research_registry.json`. No cross-pair candidate is registered yet, and no strategy/backtest was created by this governance work. Focused test: `1 passed`.
## Four-pair scope correction (2026-08-31)

- The target multi-pair research universe is exactly **EURUSD, GBPUSD, USDJPY, and USDCAD**. EURUSD was mistakenly omitted from the newer cross-pair constants because it already had completed research/calibration history; it is not excluded from the project goal.
- EURUSD now has a saved RoboForex ECN New York spread report: 3,313 fresh records, median 1 point, p95 2 points, maximum 4 points. Its frozen research base/stress model is 2/1/3 and 4/2/3 for spread points/slippage points/USD commission per lot per side. The USD 3 commission is a conservative 1.50 USD/EUR notional ceiling under the published 20/mio schedule.
- `CrossPairDevelopmentSpec`, the read-only cost audit, and the session-movement diagnostic now all cover four pairs. The 2019-2023 EURUSD annual archive already existed and is validated. No strategy evaluation was run as part of this correction.
## Strategy 18 four-pair preregistration (2026-08-31)

- `london_asian_range_failed_auction` is prospectively registered in `config/cross_pair_research_registry.json` as `strategy_18_london_asian_range_failed_auction_v1`, `PROPOSED / UNDECIDED`, with no implementation and no experiment evidence.
- Governing brief: `docs/STRATEGY_18_RESEARCH_BRIEF.md`. It is a low-turnover Europe/London failed-auction hypothesis: form 00:00-05:59 Asian range, require 07:00-09:00 M5 sweep at least 8 pips outside, require one of the next three M5 closes at least 1 pip inside, enter opposite on next M1 open; 8-25 pip structural stop, 2R / >=16 pip target, one daily intent, and 12:00 London hard exit.
- The exact same frozen rule set applies to EURUSD, GBPUSD, USDJPY, and USDCAD. Pair-specific frozen base/stress costs are required; no pair may be selected after seeing results. Every pair must meet the declared per-pair gates and the four-pair aggregate must be stress-profitable with no individual pair negative.
- Registration command: `scripts/preregister_strategy18.py`. It is idempotent and validates the strict multi-pair registry atomically. It did not create strategy code, load historical data, or access MT5.
- Next permitted action after review is implementation plus deterministic unit tests, followed by development-only evaluation. No 2024-2026 data, live/demo execution, or parameter adjustment is authorized.
## Strategy 18 four-pair implementation checkpoint (2026-08-31)

- Strategy 18 is preregistered as `strategy_18_london_asian_range_failed_auction_v1` for EURUSD, GBPUSD, USDJPY, and USDCAD only. Its frozen brief is `docs/STRATEGY_18_RESEARCH_BRIEF.md`.
- Implemented signal: `src/mt5_scalping_agent/backtesting/london_asian_range_failed_auction.py`. It uses the completed London Asian range, an M5 sweep/re-entry confirmation, a structural stop, 2R target, a one-intent-per-date limit, and frozen pair stress-cost gates. It has no MT5, broker, or order-submission code.
- Added guarded runner: `scripts/run_strategy18_development.py`. It verifies the preregistration, accepts no date-range argument, uses exactly `[2019-01-01, 2024-01-01)`, loads all four audited broker contracts, and applies their frozen base/stress models. It explicitly marks 2024+ as not loaded.
- Added an optional `is_evaluation_time(timestamp)` backtest scheduling hook. Strategy 18 uses it to avoid constructing candle histories outside completed M5 London decision points. Existing strategies retain prior behavior unless they implement the hook.
- Verification after implementation: `321 passed`.
- No Strategy 18 development report exists yet. Two full eight-scenario attempts were intentionally stopped before any scenario completed because the generic M1 engine did not provide timely progress. No Python process remains and no partial report should be treated as evidence.
- Next engineering action: add annual scenario checkpoints/progress to the Strategy 18 runner, then run only the frozen 2019-2023 development evaluation. Do not tune its rules, select a preferred pair, load 2024-2026, or enable broker execution.
## Strategy 18 early-stop rejection (2026-08-31)

- The checkpointed development runner completed the first required window only: EURUSD, base costs, calendar year 2019. It produced 2 accepted trades.
- The frozen primary gate requires 50-220 accepted trades in every pair-year. EURUSD 2019 therefore fails unambiguously before any economic comparison.
- The runner was intentionally stopped immediately. No other pair, year, stress scenario, robustness diagnostic, or 2024-2026 data was evaluated.
- Decision: `REJECTED_PRIMARY_GATES`. Do not tune Strategy 18, select EURUSD or any other pair from it, or resume its remaining scenarios.
- Formal decision record: `reports/strategy18/strategy18_early_stop_rejection.json`. The annual checkpoint remains provenance only and is not a final report.
## Strategy 18 registry closure (2026-08-31)

- `config/cross_pair_research_registry.json` now records Strategy 18 as `REJECTED`, with its implementation path and immutable early-stop evidence rather than leaving it misleadingly `PROPOSED`.
- `CrossPairProposal` now supports only two consistent states: a clean `PROPOSED` record with no implementation/evidence, or `REJECTED` with both implementation and recorded evidence. Unsupported lifecycle states are refused.
- Recorder: `scripts/record_strategy18_rejection.py`; evidence: `reports/strategy18/strategy18_early_stop_rejection.json`.
- Verification: `321 passed`.
- All currently registered cross-pair candidates are closed. Per the autonomous operating contract, do not create another strategy without explicit user review of a new prospective hypothesis and frozen gates.
## Phase 19B conditional edge validation (2026-08-31)

- Phase 19B is complete as a `POST_DISCOVERY_DIAGNOSTIC`, not untouched validation and not a new strategy. It used only EURUSD, GBPUSD, USDJPY, and USDCAD data in `[2019-01-01, 2024-01-01)`. No MT5, execution, trade simulation, PnL, equity, or strategy-registry action occurred.
- Implementation: `src/mt5_scalping_agent/research/conditional_edge_validation.py`; runner: `scripts/run_phase19b_conditional_validation.py`; specification: `docs/PHASE_19B_RESEARCH_SPEC.md`; tests: `tests/test_conditional_edge_validation.py`.
- Reports: `reports/phase19b/phase19b_summary.json` plus event attrition, path, session, lead-lag, cost-opportunity, stability, and GBPUSD diagnostic reports.
- The original Phase 19A GBPUSD acceptance observation remains negative at 5/10/15/30/60 minutes. At 15 minutes it is `-0.2485` pips across 1,333 deduplicated events, and every leave-one-year-out mean remains negative (`-0.1895` to `-0.3816` pips).
- The strongest predefined cross-pair lead-lag correlation has absolute magnitude `0.0081`, which is economically negligible. This diagnostic does not identify a credible conditional predictive effect.
- Decision: `CLOSE_FAMILY`. Do not create Strategy 19, tune existing rules, or treat Phase 19B as strategy evidence. The complete suite is `332 passed` (two pre-existing Phase 19A pandas deprecation warnings).
## Phase 20A intraday path and liquidity behaviour discovery (2026-08-31)

- Phase 19 remains closed. Phase 20A opened a distinct descriptive research family; it did not create Strategy 19, Strategy 20, a registry candidate, a trade simulation, or any execution capability.
- Scope: validated Dukascopy M1 EURUSD, GBPUSD, USDJPY, and USDCAD data only in `[2019-01-01, 2024-01-01)`. The manifest fingerprints all 20 annual input archives. MT5 and 2024-2026 data were untouched.
- Implementation: `src/mt5_scalping_agent/research/intraday_path_discovery.py`; runner: `scripts/run_phase20a_path_discovery.py`; specification: `docs/PHASE_20A_RESEARCH_SPEC.md`; tests: `tests/test_intraday_path_discovery.py`.
- Reports: `reports/phase20a/`. Primary events are sampled only after completed M5 observations and de-duplicated by 60 minutes: roughly 372k raw M5 observations and 31.2k primary events per pair.
- Classification: `PATH_STRUCTURE_ONLY`. The only FDR-surviving, stress-friction-material diagnostic was USDCAD's highest 15-minute volatility bucket: 60-minute continuation was lower than the same-pair comparison by `-1.47` pips (95% day-block-bootstrap CI `[-2.36, -0.57]`, FDR q `0.0192`). This is evidence against simple continuation in that state, not a trading rule or edge.
- No other predeclared volatility, path-efficiency, or volatility-change comparison survived FDR. The analysis therefore does not justify prospective strategy design.
- Verification: `4 passed` focused Phase 20A tests and `336 passed` complete project tests. Two existing Phase 19A pandas deprecation warnings remain.
- STOP for human research review. Do not automatically continue to Phase 20B or create any strategy.
## Phase 21A and Phase 21B status (2026-08-31)

- Phase 21A's original zero-event result was invalidated. Root cause: causal residual percentile calculation required 5,761 consecutive non-missing aligned M5 rows. Legitimate cross-pair calendar gaps prevented percentile eligibility.
- Repair: Phase 21A now ranks each residual against the prior 20 trading days of valid residual observations. The lookback, Method A residual definition, buckets, event-entry rule, and 60-minute deduplication were unchanged.
- Valid eligibility after repair: each pair has 344,412 valid percentiles, all fixed 90+ buckets populated, 26,751-27,123 bucket entries, and 12,313-12,920 deduplicated events.
- Phase 21A's limited completed Method A 60-minute diagnostic found negative absolute residual changes for all four pairs with FDR q=0. It is currently labelled `RELATIVE_STRUCTURE_ONLY`; this is descriptive and not strategy approval. Broader H2-H6, economic, and attribution evidence remains incomplete.
- Phase 21B was explicitly approved as a research-only convergence-mechanism follow-up. Files: `docs/PHASE_21B_RESEARCH_SPEC.md`, `src/mt5_scalping_agent/research/convergence_mechanism.py`, `scripts/run_phase21b_convergence_mechanism.py`, and `tests/test_convergence_mechanism.py`.
- Phase 21B status is `INCOMPLETE_EVIDENCE`: initial target-reversal/common-catch-up/both/ambiguous attribution and path metrics are implemented, but stability, six-pair comparison, frozen-cost context, bootstrap/FDR, and a final Phase 21B classification have not been completed.
- No Phase 21A or 21B work accessed 2024+, MT5, broker execution, strategy PnL, equity curves, or created a strategy/registry candidate. Do not interpret either phase as approval for trading.