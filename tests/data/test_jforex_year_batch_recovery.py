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


def test_java_exporter_contains_atomic_recovery_and_validated_protection() -> None:
    source = Path("jforex/Phase22TickExporter.java").read_text(encoding="utf-8")
    assert '"YEAR_BATCH".equalsIgnoreCase' in source
    assert 'Files.deleteIfExists(activeTemporary.toPath())' in source
    assert 'StandardCopyOption.ATOMIC_MOVE' in source
    assert 'existing unprotected monthly file' in source
    assert 'protectedMonths.contains(month)' in source
    assert "IEngine" not in source
    assert "submitOrder" not in source
