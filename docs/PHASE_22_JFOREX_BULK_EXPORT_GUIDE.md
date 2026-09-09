# Phase 22 JForex Year-Batch Export Workflow

Phase 22 remains governed by the immutable 240-unit monthly manifest. The `YEAR_BATCH` exporter reduces manual JForex work to one run per pair and calendar year while producing the same twelve calendar-month UTC files expected by that manifest. JForex interaction remains manual; the repository does not automate the GUI or login.

## Run one pair-year

1. From the repository root, run:

   ```powershell
   .\.venv\Scripts\python.exe scripts\next_jforex_bulk_batch.py
   ```

2. Compile the current `jforex/Phase22TickExporter.java` in JForex4. Do not reuse an older compiled `.jfx` after the Java source changes.
3. In Strategy Tester select `Phase22TickExporter`, **Ticks**, **Process all ticks**, no interpolation, no optimization, and only the instrument printed by the helper.
4. Set `Mode` to `YEAR_BATCH`, then copy the printed batch year, start, exclusive end, output directory, and protected validated months into the exporter.
5. Run that pair-year synchronously to completion. Files are streamed through a `.part` name and finalized month by month. The exporter refuses to overwrite an unprotected final file and skips only months explicitly listed as validated.
6. Import every completed file with:

   ```powershell
   .\.venv\Scripts\python.exe scripts\import_jforex_ticks.py --bulk
   ```

7. Check progress with:

   ```powershell
   .\.venv\Scripts\python.exe scripts\jforex_bulk_progress.py
   ```

8. Resolve any `FAILED` monthly unit before starting another pair-year. Repeat until all 240 units are `VALIDATED`. Do not export 2024 or later.

The already validated EURUSD January 2019 unit must be supplied as protected month `1` for the EURUSD 2019 run. It is never overwritten or regenerated.

## Recovery and invariants

- The monthly UTC intervals are half-open: `[month_start, next_month_start)`.
- A tick at exactly midnight belongs only to the new month.
- `source_sequence` restarts at zero for each monthly output, matching a standalone monthly export.
- A stale `.part` file for the active month is removed before that month is restarted; a completed final CSV is never silently replaced.
- The exporter holds only the active output stream, not a year of ticks in memory.
- A failure in one imported file does not prevent `--bulk` from validating other completed files.

The authoritative manifest is `reports/phase22_data_build/jforex_bulk_export_manifest.json`. It contains exact UTC bounds, filenames, landing paths, validation state, and hashes for every monthly unit. Reports and market data are intentionally Git-ignored.
