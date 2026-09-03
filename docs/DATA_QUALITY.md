# M1 Data Quality and Session Semantics

## Provider boundary

The accepted archive lineage is deterministic:

| UTC period | Accepted provider | Timestamp basis |
| --- | --- | --- |
| Through 2018-12-31 | HistData | Fixed EST converted to UTC; not New York DST time |
| From 2019-01-01 | Dukascopy | Native UTC |

`LocalResearchArchive` rejects a request crossing `2019-01-01T00:00:00Z`. It also
selects Dukascopy for every post-boundary request, so an unexpected HistData file
cannot become an implicit fallback.

The alleged HistData annual files for 2019-2026 are **not present** in the current
workspace. `data/histdata` contains accepted annual CSVs for 2003-2018 and a
manifest named `EURUSD_m1_2019_2019_manifest.json`. That manifest reports no
accepted file and records rejection of the 2019 download because duplicate
timestamps failed OHLCV validation. No 2020-2026 HistData annual CSV or manifest
was found. Nothing was deleted, moved, or repaired during this audit. The generated
inventory will flag any post-boundary HistData file if one appears later.

## Audit definitions

Run:

```powershell
.\.venv\Scripts\python.exe scripts\audit_m1_archive.py
```

The report records, per annual file and in aggregate:

- expected and observed minutes;
- scheduled-closed and missing active-market minutes;
- duplicate and malformed timestamps;
- off-minute timestamps;
- malformed OHLC geometry and invalid tick volumes;
- gap count, longest gap, and missing minutes by UTC date and DST-aware session;
- provider provenance.

Expected minutes use the standard continuous FX week from Sunday 17:00 through
Friday 17:00 `America/New_York`, which follows US DST. Public holidays and unusual
provider closures are not inferred. A one- or two-minute active-market gap bounded
by observed adjacent minutes is labelled `possible_no_tick`; this is a heuristic,
not proof. Longer or unbounded active-market absences remain `unexplained` rather
than being declared corrupt.

## M5 completeness

`resample_m1_to_m5` counts the M1 constituents in every nonempty five-minute
bucket and returns `m1_count` and `is_complete` metadata.

- Default `incomplete="drop"`: excludes incomplete buckets and records counts and
  examples in `DataFrame.attrs`.
- `incomplete="raise"`: rejects the first incomplete bucket.
- `incomplete="keep"`: retains the bucket with `is_complete=False` for explicit
  quality inspection.

Therefore a partial bucket is never silently presented as an ordinary complete M5
candle. Empty market-closure buckets are not candles and are not synthesized.

## DST-aware sessions

Research diagnostics define each sampling window in local civil time:

| Session | Local window | Winter UTC | Summer UTC |
| --- | --- | --- | --- |
| London | 08:00-13:00 `Europe/London` | 08:00-13:00 | 07:00-12:00 |
| New York | 08:00-13:00 `America/New_York` | 13:00-18:00 | 12:00-17:00 |

Real overlap during the different UK/US DST transition weeks is preserved as
`london_new_york`. Existing strategy rules are frozen research rules and were not
changed in this infrastructure phase; new diagnostics and future evaluation code
must use the DST-aware utilities rather than fixed UTC-hour classification.
