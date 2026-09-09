from pathlib import Path

from mt5_scalping_agent.data.jforex_bulk import build_manifest, process_bulk

HEADER = "timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n"


def test_bulk_imports_multiple_files_and_isolates_partial_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    incoming = tmp_path / "incoming"
    manifest = build_manifest(manifest_path, incoming)
    january, february = manifest["units"][:2]
    incoming.mkdir()
    Path(january["landing_path"]).write_text(
        HEADER + "1546300800000,EURUSD,1.1,1.2,1,2,0\n", encoding="utf-8"
    )
    Path(february["landing_path"]).write_text(
        HEADER + "1548979200000,GBPUSD,1.1,1.2,1,2,0\n", encoding="utf-8"
    )
    result = process_bulk(manifest_path, tmp_path / "ticks")
    assert result["summary"]["VALIDATED"] == 1
    assert result["summary"]["FAILED"] == 1
    assert result["units"][0]["status"] == "VALIDATED"
    assert result["units"][1]["status"] == "FAILED"


def test_java_exporter_uses_explicit_batch_mode_and_ignores_single_dates() -> None:
    source = Path("jforex/Phase22TickExporter.java").read_text(encoding="utf-8")
    assert "enum ExportMode { SINGLE_UNIT, YEAR_BATCH }" in source
    assert "mode = ExportMode.YEAR_BATCH" in source
    assert "mode == ExportMode.YEAR_BATCH" in source
    batch_initializer = source.split("private void initializeYearBatch()", 1)[1].split(
        "private void parseProtectedMonths()", 1
    )[0]
    assert "startUtc" not in batch_initializer
    assert "endUtc" not in batch_initializer


def test_java_exporter_has_absolute_path_startup_and_unit_diagnostics() -> None:
    source = Path("jforex/Phase22TickExporter.java").read_text(encoding="utf-8")
    required = (
        "outputDirectory.isAbsolute()",
        "outputDirectory.getCanonicalFile()",
        "Files.isWritable(outputDirectory.toPath())",
        "PHASE22_EXPORT_MODE=",
        "BATCH_OUTPUT_DIRECTORY=",
        "TESTER_EXPECTED_START=",
        "MONTH_%02d=PENDING",
        "YEAR_BATCH_STARTED",
    )
    assert all(value in source for value in required)


def test_java_exporter_has_independent_writer_recovery_and_failure_visibility() -> None:
    source = Path("jforex/Phase22TickExporter.java").read_text(encoding="utf-8")
    required = (
        "initializeMonth(month)",
        "Files.deleteIfExists(activeTemporary.toPath())",
        "StandardCopyOption.ATOMIC_MOVE",
        "MONTH_WRITER_OPENED ",
        "MONTH_PROTECTED ",
        "MONTH_FINALIZED ",
        "YEAR_BATCH_COMPLETED ",
        "YEAR_BATCH_NO_OUTPUT_ERROR",
        "monthsWritten != pending",
        "protectedMonths.contains(month)",
    )
    assert all(value in source for value in required)
    assert "IEngine" not in source
    assert "submitOrder" not in source