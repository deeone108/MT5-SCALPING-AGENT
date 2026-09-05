# Phase 22 Data Source Decision

Status: `HUMAN_GATE_REQUIRED_TRUEFX_DOWNLOAD_METHOD`
Evaluation date: 2026-09-05
Scope: data engineering only; no Phase 22A research, PnL, predictive analysis, MT5 access, or 2024+ data access.

## Decision

TrueFX remains the preferred candidate, but it is not yet an approved Phase 22 source. Its public site describes free top-of-book, tick-by-tick historical FX data with fractional spreads and millisecond detail. Historical downloads require registration and login. The terms grant a limited, non-transferable license for a single download instance and internal viewing/analysis, and prohibit redistribution. They expressly discuss API use for real-time data, but do not expressly authorize automation of authenticated historical downloads. No scraping or automated acquisition was attempted.

The unauthenticated pages do not establish the native timestamp timezone, exact row schema, archive organization, or complete 2019-2023 inventory for EURUSD, GBPUSD, USDJPY, and USDCAD. Those facts must be recorded from the authenticated download catalog and provider-native files rather than guessed. The pilot therefore remains unacquired.

Primary TrueFX sources checked:

- <https://www.truefx.com/truefx-historical-downloads-2/>
- <https://www.truefx.com/truefx-market-data-faq/>
- <https://www.truefx.com/truefx-terms-and-conditions/>
- <https://www.truefx.com/truefx-registration-2/>

## Provider comparison

| Criterion | TrueFX | HistData fallback | Dukascopy |
|---|---|---|---|
| Access/license | Account and terms acceptance; internal analysis permitted; redistribution prohibited | Free manual downloads; optional paid FTP/SFTP | Automated endpoint blocked pending express provider consent |
| Automation | Historical-download automation not expressly documented | Free manual route; official FTP/SFTP route after human purchase | Not authorized for this project |
| Historical depth | Required 2019-2023 inventory unverified behind login | Provider update history supports the period; exact archive inventory still requires download-page verification | Technically deep, but access gate controls |
| Resolution | Tick-by-tick, millisecond detail | Generic ASCII ticks include milliseconds | Millisecond tick quotes |
| Bid/Ask | Top-of-book and fractional spreads imply both sides; native columns must be verified from a file | Documented `DateTime,Bid,Ask,Volume` | Bid, ask, bid volume, ask volume |
| Volume | Public historical schema unverified; never fabricate | Documented volume field; meaning/quality requires validation | Bid/ask volumes supplied by endpoint |
| Timezone | Unverified | Fixed EST (UTC-5), without DST | UTC/epoch semantics in blocked client |
| Four pairs | Public site advertises major FX coverage; exact catalog entries unverified | EURUSD, GBPUSD, USDJPY, USDCAD documented among supported pairs | Supported by blocked client |
| 2019-2023 | Unverified without authenticated catalog | Provider updates and pair/year/month archive organization support evaluation | Available in principle, not authorized |
| Download organization | Unverified without login | Pair/year/month ZIP files | Paginated service responses |
| Cost | Historical downloads advertised at zero cost | Manual downloads free; FTP/SFTP USD 27 for 15 days | No approved route/cost |
| Reproducibility risk | Account workflow and unclear automation; native metadata not yet captured | Manual repetition burden or temporary paid credentials; fixed-offset conversion required | Consent absent |
| Data-quality risk | Indicative, non-executable quotes; timezone/volume/native layout unverified | Free data has no warranty; gaps and volume semantics need audit | Indicative source and undocumented endpoint constraints |

HistData references: <https://www.histdata.com/f-a-q/data-files-detailed-specification/> and <https://www.histdata.com/download-by-ftp/>. HistData was not selected or accessed because the authorized evaluation order stops for human resolution at the TrueFX download-method gate. No purchase was made.

## Manual TrueFX action required

1. Open <https://www.truefx.com/truefx-registration-2/> in your own browser, create an account if needed, read and personally accept the current terms, and sign in.
2. Open <https://www.truefx.com/truefx-historical-downloads-2/> while signed in.
3. Before downloading, capture a screenshot or text inventory showing whether EURUSD, GBPUSD, USDJPY, and USDCAD each have every year 2019, 2020, 2021, 2022, and 2023. Also capture any displayed timezone, schema, filename, archive-layout, or API/download instructions.
4. Download only the smallest provider-native EURUSD archive that contains the frozen interval `[2019-01-07T00:00:00Z, 2019-01-14T00:00:00Z)`. Do not download 2024+ data and do not start the five-year bulk acquisition.
5. Keep the archive untouched: do not rename, unzip, convert, edit, or re-save it. Place it under `data/ticks/inbox/truefx/`, preserving its provider filename. Do not commit market data or credentials.
6. Provide the captured catalog/metadata evidence. Never provide the account password, cookies, session token, or other secrets.

After this human step, the next data-only action is to hash and inventory the native file, empirically verify schema and timezone, implement the reviewed offline parser, and run only the frozen EURUSD pilot. Bulk acquisition remains gated on pilot quality and measured storage.

## Architecture checkpoint

- `HistoricalTickSource` now separates provider availability, acquisition, timestamp semantics, schema, and licensing metadata from normalized storage.
- `TrueFxTickSource` is deliberately fail-closed and offline. It contains no HTTP code, credentials, scraper, or guessed parser; it rejects requests extending beyond 2023.
- The future normalized archive remains provider-neutral: `timestamp_utc_ns`, `pair`, `bid`, `ask`, nullable `bid_volume`, nullable `ask_volume`, `source_sequence`, `source_provider`, `source_file`, `raw_row_number`, plus derived spread and midpoint fields.
- Missing volume remains null. No forward fill, interpolation, synthetic ticks, or mixed-provider primary dataset is permitted.

## Current evidence

- TrueFX four-pair availability: unverified behind authenticated catalog.
- TrueFX 2019-2023 availability: unverified behind authenticated catalog.
- Pilot acquisition/tick count/quality: not run / 0 / unavailable.
- Compression and projected full storage: unavailable until a lawful pilot measures bytes per tick.
- Selected primary provider: none yet.
- Final gate: `HUMAN_GATE_REQUIRED_TRUEFX_DOWNLOAD_METHOD`.
