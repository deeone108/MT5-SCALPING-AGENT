# Phase 22 JForex Bulk Export Workflow

The Phase 22 dataset is partitioned into 240 calendar-month UTC units: four pairs × five years × twelve months. JForex interaction remains manual; repository-side discovery, filenames, validation, normalization, manifests and hashing are automated.

1. Run `.\.venv\Scripts\python.exe scripts\next_jforex_bulk_unit.py` from the repository root.
2. In JForex4 Strategy Tester select `Phase22TickExporter`, **Ticks**, **Process all ticks**, no interpolation, no optimization, and only the printed instrument.
3. Copy the printed start, exclusive end, and output path into the exporter parameters. The exporter refuses to overwrite an existing file.
4. Run that single monthly export to completion.
5. From the repository run `.\.venv\Scripts\python.exe scripts\import_jforex_ticks.py --bulk`.
6. Resolve any `FAILED` unit before continuing. A `VALIDATED` unit with matching raw and normalized hashes is skipped on subsequent scans.
7. Repeat from step 1. Do not export 2024 or later.

The authoritative manifest is `reports/phase22_data_build/jforex_bulk_export_manifest.json`. It was generated before bulk export and contains exact UTC bounds, filenames, landing paths and status for every unit. Reports and market data are intentionally Git-ignored.

No generated JForex preset is supplied because current official documentation does not define a stable external preset-import format. The next-unit helper avoids guessing that interface while reducing each owner cycle to four copy-ready parameters.
