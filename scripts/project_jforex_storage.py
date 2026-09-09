"""Project Phase 22 storage from the immutable real-pilot evidence."""

import json
import shutil
from pathlib import Path

PILOT = Path("data/ticks/manifests/jforex_pilot_quality.json")
OUTPUT = Path("reports/phase22_data_build/jforex_storage_projection.json")

pilot = json.loads(PILOT.read_text(encoding="utf-8"))
ticks_per_day = pilot["ticks"] / 7
ticks_per_pair_year = ticks_per_day * 365.2425
raw_pair_year = ticks_per_pair_year * pilot["raw_bytes_per_tick"]
parquet_pair_year = ticks_per_pair_year * pilot["parquet_bytes_per_tick"]
raw_full = raw_pair_year * 20
parquet_full = parquet_pair_year * 20
combined = raw_full + parquet_full
document = {
    "basis": "real EURUSD frozen pilot", "ticks_per_day": ticks_per_day,
    "estimated_ticks_per_pair_year": ticks_per_pair_year,
    "estimated_raw_bytes_per_pair_year": raw_pair_year,
    "estimated_parquet_bytes_per_pair_year": parquet_pair_year,
    "estimated_raw_bytes_four_pairs_five_years": raw_full,
    "estimated_parquet_bytes_four_pairs_five_years": parquet_full,
    "estimated_combined_bytes": combined, "required_with_25_percent_headroom_bytes": combined * 1.25,
    "free_disk_bytes": shutil.disk_usage(Path.cwd()).free,
}
document["storage_gate_passed"] = document["required_with_25_percent_headroom_bytes"] < document["free_disk_bytes"]
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(OUTPUT)
