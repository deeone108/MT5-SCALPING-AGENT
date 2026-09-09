from pathlib import Path

from mt5_scalping_agent.data.jforex_bulk import build_manifest, dataset_roots, process_bulk


HEADER = "timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n"


def test_manifest_has_exact_utc_months_and_240_units(tmp_path: Path) -> None:
    manifest = build_manifest(tmp_path / "manifest.json", tmp_path / "incoming")
    assert manifest["expected_units"] == 240
    assert manifest["units"][0]["expected_filename"] == "EURUSD_20190101T000000Z_20190201T000000Z_JFOREX_TICKS.csv"
    assert manifest["units"][11]["end_utc"] == "2020-01-01T00:00:00Z"
    assert manifest["units"][-1]["end_utc"] == "2024-01-01T00:00:00Z"
    assert {unit["status"] for unit in manifest["units"]} == {"PENDING"}


def test_bulk_matches_imports_and_skips_hash_verified_unit(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    incoming = tmp_path / "incoming"
    manifest = build_manifest(path, incoming)
    unit = manifest["units"][0]
    source = Path(unit["landing_path"])
    source.parent.mkdir(parents=True)
    source.write_text(HEADER + "1546300800000,EURUSD,1.1,1.2,1,2,0\n", encoding="utf-8")
    first = process_bulk(path, tmp_path / "ticks")
    assert first["summary"]["VALIDATED"] == 1
    normalized = Path(first["units"][0]["normalized_path"])
    before = normalized.stat().st_mtime_ns
    second = process_bulk(path, tmp_path / "ticks")
    assert second["summary"]["VALIDATED"] == 1
    assert normalized.stat().st_mtime_ns == before


def test_wrong_month_and_pair_fail_and_roots_are_stable(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    incoming = tmp_path / "incoming"
    manifest = build_manifest(path, incoming)
    unit = manifest["units"][0]
    source = Path(unit["landing_path"])
    source.parent.mkdir(parents=True)
    source.write_text(HEADER + "1548979200000,GBPUSD,1.1,1.2,1,2,0\n", encoding="utf-8")
    result = process_bulk(path, tmp_path / "ticks")
    assert result["summary"]["FAILED"] == 1
    rows = [{"pair": "EURUSD", "year": 2019, "month": month, "status": "VALIDATED",
             "raw_sha256": f"raw{month}", "normalized_sha256": f"norm{month}", "ticks": month}
            for month in (1, 2)]
    assert dataset_roots(rows) == dataset_roots(list(reversed(rows)))
    assert dataset_roots(rows)["dataset"] is None
