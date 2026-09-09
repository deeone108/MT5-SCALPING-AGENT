# Phase 22 FXCM Source Decision

Status: `HUMAN_GATE_REQUIRED_FXCM_SOURCE_VERIFICATION`

Evaluation date: 2026-09-09. This was data-source verification only. No Phase 22A research, signals, PnL, optimization, MT5 access, or broker execution occurred.

## Official documentation

The source owner is FXCM/Stratos Group. FXCM's verified GitHub organization hosts the public `fxcm/MarketData` repository. Its `TickData` directory states:

- free access to historical tick data;
- provider location `https://tickdata.fxcorporate.com/{instrument}/{year}/{week}.csv.gz`;
- data from January 2019, organized by trading instrument and week;
- years 2019 through 2023 and weeks 1 through 52/53;
- EURUSD, GBPUSD, USDJPY, and USDCAD among the instruments;
- timestamps in UTC;
- indicative data based on Active Trader account spreads;
- personal use subject to FXCM's EULA.

Authoritative references checked:

- <https://github.com/fxcm/MarketData/tree/master/TickData>
- <https://github.com/fxcm/MarketData>

The repository's top-level README now says tick-data users should email `premiumdata@fxcm.com`, which conflicts with the more specific TickData directory's free-access statement. The weekly URL convention in the top-level README applies to candle data, not tick data.

## Live access result

The frozen EURUSD pilot interval is `[2019-01-07T00:00:00Z, 2019-01-14T00:00:00Z)`, corresponding to ISO week 2 of 2019. Exactly one candidate provider file was requested:

`https://tickdata.fxcorporate.com/EURUSD/2019/2.csv.gz`

On 2026-09-09 the endpoint returned a Cloudflare Access **Sign in** HTML document instead of gzip content. Response bytes were 32,865 and SHA-256 was `9a7809b53e17412539e0ef9b988914b9a235e4f2da5b11dd63daf53b93093dd4`. Gzip validation failed immediately on the HTML `<!` signature. The response was held only in a temporary directory and removed after recording this evidence.

No attempt was made to bypass Cloudflare Access, discover private endpoints, supply guessed credentials, use an unofficial mirror, or download another file.

## Unresolved gates

- A currently authorized way to access `tickdata.fxcorporate.com` is not documented in the official repository.
- The actual pilot CSV schema cannot be inspected, so Bid and Ask availability remains unverified.
- Timestamp precision cannot be confirmed from pilot evidence; only the documented UTC timezone is known.
- Pilot quality, duplicates, gaps, Parquet compression, replay determinism, and storage projection cannot be measured.
- No `FxcmTickSource` parser or downloader should be implemented against an unavailable and uninspected source.

## Human resolution required

Obtain current written access instructions from FXCM using `premiumdata@fxcm.com` or `api@fxcm.com`, specifically asking whether the historical weekly tick archive remains available for free personal research, how Cloudflare Access should be authenticated, and whether the files contain UTC timestamp, Bid, and Ask columns for the four required pairs throughout 2019-2023. Do not send credentials through repository files, reports, or chat.

Alternatively, if the URL works in the user's authorized browser session, manually download only `EURUSD/2019/2.csv.gz` without changing it and provide the native file for offline verification. Browser cookies, tokens, and credentials must not be provided.

Full acquisition remains prohibited until official access, schema, coverage, pilot quality, replay, and storage gates all pass.
