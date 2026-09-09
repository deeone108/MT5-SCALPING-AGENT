# Phase 22 JForex4 Manual Tick Export Guide

Status: `JFOREX_MANUAL_TICK_EXPORT_SUPPORTED`

This workflow uses the current **JForex4 Desktop** Strategy Tester interactively. Dukascopy documents that the tester uses tick-after-tick historical data, that demo-platform historical data comes from the LIVE environment, and that `ITick` provides epoch-millisecond time, best Bid, best Ask, bid volume, and ask volume. A free demo login is therefore sufficient in principle; the owner must confirm that the frozen 2019 pilot loads in their session.

Dukascopy does not document a maximum tick-export period or a built-in raw-tick CSV export limit. The tester supports configurable sample periods, and exports can be split by any chosen period. Start with one week only. Large `getTicks` calls are specifically discouraged because they can exhaust memory; this exporter instead receives `onTick` events sequentially.

Official references:

- <https://www.dukascopy.com/wiki/en/manuals/jforex4-desktop/strategy-tester/>
- <https://www.dukascopy.com/wiki/en/manuals/jforex4-desktop/strategies/>
- <https://www.dukascopy.com/wiki/en/development/strategy-api/historical-data/overview-historical-data/>
- <https://www.dukascopy.com/wiki/en/development/strategy-api/historical-data/history-ticks/>
- <https://www.dukascopy.com/client/javadoc3/com/dukascopy/api/ITick.html>

## Export exactly one pilot

1. Install/open the current 64-bit JForex4 Desktop application using Dukascopy's official installation page (<https://www.dukascopy.com/wiki/en/manuals/jforex4-desktop/installation/>) and sign in to an eligible demo or live account yourself. Codex must not handle the login.
2. Confirm the account is **DEMO** if you do not intend to use a live account. Do not submit or enable orders.
3. Open `View â†’ Strategies`.
4. Choose the local import/open action and select `jforex/Phase22TickExporter.java` from this repository. If JForex imports source into JCloud, verify the displayed source matches the local file.
5. Select the strategy and click **Compile**. Continue only after `Compiling... OK`.
6. Open `View â†’ Strategy Tester` (called Historical Tester in older documentation).
7. Select `Phase22TickExporter`.
8. Open **Instruments** and select **EUR/USD only**.
9. Set **Sample Period** from `2019-01-07 00:00:00 UTC` through `2019-01-14 00:00:00 UTC`.
10. Set **Time Frame** to **Ticks** and select **Process all ticks**. Do not choose candle interpolation or any tick-skipping filter.
11. Leave Visual Mode and Optimization disabled.
12. Click **Start**. In Define Parameters set:
    - Instrument: `EUR/USD`
    - Output CSV: a local path you control, such as `C:\Users\derek\Desktop\Vcodeee\data\ticks\incoming\jforex\EURUSD_20190107T000000Z_20190114T000000Z_JFOREX_TICKS.csv`
    - Start UTC inclusive: `2019-01-07 00:00:00.000`
    - End UTC exclusive: `2019-01-14 00:00:00.000`
13. Click **Run** and wait for completion. The strategy contains no `IEngine`, order submission, or trading logic. File access may trigger JForex's full-access confirmation because writing a local CSV requires it.
14. Do not edit, rename, sort, or re-save the CSV. Import it from the repository terminal:

    `.\.venv\Scripts\python.exe scripts\import_jforex_ticks.py --pilot`

The CSV schema is `timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence`. The timestamp is the JForex `ITick.getTime()` Unix epoch millisecond value and is normalized deterministically to UTC. Bid/Ask and their corresponding best-price volumes are preserved without reconstruction.

Do not export other weeks, pairs, years, or 2024+ data until the pilot has passed parser, quality, replay, and storage validation.
