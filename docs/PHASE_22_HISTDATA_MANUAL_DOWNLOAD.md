# Phase 22 HistData Manual Download

Status: `HUMAN_GATE_REQUIRED_HISTDATA_MANUAL_DOWNLOAD`

HistData's official free workflow exposes **Generic ASCII / Tick Data** through a multi-step browser selector. The public site does not expressly authorize automated submission of that workflow. No form scraping, private endpoint use, CAPTCHA handling, or archive download has been attempted.

Sources checked 2026-09-09:

- <https://www.histdata.com/download-free-forex-data/>
- <https://www.histdata.com/f-a-q/data-files-detailed-specification/>
- <https://www.histdata.com/download-by-ftp/>

## Download only the frozen pilot archive

1. In a normal browser, open <https://www.histdata.com/download-free-forex-data/>.
2. Select **Generic ASCII**, then **Tick Data**. Do not select MetaTrader M1, Excel M1, or NinjaTrader one-second data.
3. Select **EUR/USD**, year **2019**, and month **January**.
4. Download the provider ZIP using the page's normal download control. Do not rename, unzip, edit, or re-save it.
5. Keep the browser-reported filename and, if shown, capture the file-status/gap information.
6. Run:

   `python scripts/import_histdata_ticks.py C:\path\to\downloaded-file.zip`

Only January 2019 EURUSD is requested now. Do not download the other 239 units until the pilot passes schema, UTC conversion, deterministic replay, quality, and storage gates.

The importer identifies the pair and month from the contained provider CSV, verifies ZIP integrity, hashes and preserves the native archive, validates `DateTime,Bid,Ask,Volume`, converts fixed UTC-05:00 to UTC without DST, and writes Zstandard Parquet when a supported Pandas Parquet engine is installed. It never contacts HistData.

The complete frozen matrix is generated at `reports/phase22_data_build/histdata_required_files.json`. Expected outer ZIP naming is recorded only as a browser-verification aid; the importer does not trust or require it. The provider-documented inner CSV pattern is `DAT_ASCII_<PAIR>_T_<YYYYMM>.csv`.

No credentials or paid service are required. Data and reports are Git-ignored and must not be committed.
