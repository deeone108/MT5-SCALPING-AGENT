# XAU-60 pinned-source provenance

Status: `SOURCE_ACQUIRED_PENDING_ADAPTER_IMPLEMENTATION`

This evidence resolves the prior source-availability gate only. The earlier BOT-03 blocked result and commits remain correct historical evidence. No adapter, backtest, market-data access, optimization, execution integration, or LIVE change is part of this snapshot.

## Repository identity

- Human authorization: `XAU60_PUBLIC_SOURCE_ACCESS`
- Authorized and canonical URL: `https://github.com/lordgaruda/XAU-60`
- Remote `HEAD`: `refs/heads/main`
- Resolved default branch: `main`
- Pinned commit: `b877fdb1fcc5888b1443cf0214ea89f8040e8096`
- Upstream Git tree: `3f50c25f048876650c1735dd645f358981529ab4`
- Fetch timestamp: `2026-09-14T00:07:31Z`
- License: MIT, immutable Git-blob `LICENSE` SHA-256 `3b16cae9c4651b3710152d98b3c8cac75a9268ab230333538a131466927cb805`
- Selected snapshot SHA-256: `ea6f51dc468e2baec323ba5b37ee7e37543a897cef99db546f8a63ef10858dd7`
- Deterministic manifest: `reports/bot_xau60_source_manifest.json`

The snapshot lives at `third_party/xau60/b877fdb1fcc5888b1443cf0214ea89f8040e8096/`. The upstream bytes are under `source/`; adjacent `THIRD_PARTY_SOURCE` and `READ_ONLY_REFERENCE` markers identify its status. The selected source files are byte-preserved and must not be edited in place. Canonical bytes are the immutable Git blob bytes. The scoped `.gitattributes` rule `source/** -text` prevents checkout conversion, including with Windows `core.autocrlf=true`.

## Integrity correction

The original acquisition recorded selected-snapshot root `9da0c41f95f99da967c3bc543b370b0513c95529ee97eb70731768291223f7f0` and license hash `48465bd353ff6f3baaa8293f12d1cee63e30e4669739f673497886dfe972430d`. Those values were calculated from CRLF working-tree representations while Git stored LF blobs. Incident `BOT-03-XAU60-SNAPSHOT-INTEGRITY-001` therefore withheld adapter assignment.

BOT-03-SOURCE-002 corrects the manifest to the already committed Git blob bytes. It does not replace, download, normalize, or otherwise alter any selected source payload, and it preserves the original acquisition record as historical evidence. The upstream URL, pinned commit, tree identity, selected file set, strategy interpretation, and acquisition timestamp are unchanged.

## Minimum complete strategy closure

Included are the three strategy modules, their exact YAML configurations, directly imported indicator/helper modules, the abstract strategy contract and signal/position data types, `requirements.txt`, README navigation evidence, and MIT attribution. The project-native adapter must not import or adopt upstream execution, account, risk, connector, UI, alert, or runtime code.

Python package initializer files are deliberately excluded: upstream `core/__init__.py` imports its connector, risk manager, and trade executor, which would pull in the parallel platform explicitly excluded by the owner. Future adapters must port and test the selected source behavior behind this project's interfaces; they must not run the third-party package as a bot.

External packages actually imported by the selected closure are pandas, NumPy, `ta`, and (for CRT) pytz. Standard-library dependencies are recorded by the source itself.

## Strategy verification

### SMC Scalper v2.1

`FOUND_IN_SOURCE`: class `SMCScalper`, version `2.1.0`, `strategies/smc_scalper.py` lines 76–623; configuration `config/strategies/smc_scalper.yaml`; XAUUSD/M15.

The source requires CHoCH then a same-direction FVG, optionally recognizes an order block, checks proximity to the FVG midpoint, applies structure/EMA context, RSI, ADX, ATR-volatility, session, spread, and quality filters, and constructs BUY/SELL signals at the FVG midpoint. Stops use ATR or fixed distance; targets prefer a qualifying order-block level and otherwise use configured risk/reward. Exit/trailing behavior is in lines 534–621. Direct helpers: `indicators/smc_utils.py`, `indicators/common.py`, and `core/strategy_base.py`. Observed columns: open, high, low, close, volume, spread, time, with optional symbol metadata.

Important configuration discrepancy: the checked-in YAML supplies core CHoCH/FVG/order-block/risk/session values but omits the source's `filters` block. Therefore source defaults—not README prose—activate several filters. Adapter work must preserve this distinction and record its chosen configuration-loading semantics without tuning.

### Trend Break + Trauma + RSI v2.1

`FOUND_IN_SOURCE`: class `TrendBreakTrauma`, version `2.1.0`, `strategies/trend_break_trauma.py` lines 78–689; configuration `config/strategies/trend_break_trauma.yaml`; XAUUSD/H1.

The source gates on EMA21 (“Trauma”), 8/21/50 EMA stack, trend-line breakout/breakdown freshness and displacement, optional MACD/ADX/volume checks, RSI ranges, session and quality scoring. It creates directional signals with ATR-derived or fixed SL/TP and has RSI/divergence/time/trailing exit logic. Direct helpers: `indicators/trend_utils.py`, `indicators/common.py`, and `core/strategy_base.py`. Observed columns: open, high, low, close, volume, and time.

The YAML omits several nested source options, so code defaults control EMA-stack, breakout, filter, ATR SL/TP, and quality behavior unless explicitly provided. This is a source/config fact, not permission to optimize.

### CRT + TBS v2.1

`FOUND_IN_SOURCE`: class `CRTStrategy`, version `2.1.0`, `strategies/crt_tbs.py` lines 116–886; configuration `config/strategies/crt_tbs.yaml`; XAUUSD M5 entry with H1 range context.

The source builds a 00:00–06:00 UTC Asian range, permits configured London/NY killzones, detects upper/lower liquidity sweeps closing back inside the range, scores rejection/volume/sweep quality, applies range, ATR, EMA-bias, overextension, per-killzone and daily limits, and constructs opposing directional signals. Stops sit beyond the sweep; targets use the opposite range boundary where valid or fixed risk/reward. Optional midpoint and 20:00 UTC time exits plus trailing behavior are present. Direct helpers: `indicators/common.py` and `core/strategy_base.py`. Observed columns: open, high, low, close, volume, and time.

The compact YAML omits several source-default controls (sweep/range/HTF/exit/filter settings), so source defaults remain behaviorally material.

## Provenance and safety boundaries

The full upstream Git tree hash identifies the complete pinned repository. The selected snapshot hash identifies the deliberately limited source closure using UTF-8 sorted records `path NUL git_blob_sha256 NUL git_blob_size LF`. Individual file hashes are in the JSON manifest.

This acquisition did not access market data, enumerate protected partitions, reopen Phase 22, perform profitability analysis, optimize parameters, import the upstream execution platform, or enable broker/LIVE functionality.

## Handoff

Next work is independent source-integrity QA. Adapter assignment remains withheld until QA reproduces all 13 Git blob hashes and sizes, the aggregate root, license hash, pinned source identity, and Windows checkout equivalence. A later, separately assigned Research Implementer task may create project-native, provenance-linked adapters only after that gate passes.
