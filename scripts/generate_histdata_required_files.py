"""Generate the frozen Phase 22 manual-download matrix without network access."""

from __future__ import annotations

import json
from pathlib import Path

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")
OUTPUT = Path("reports/phase22_data_build/histdata_required_files.json")


def main() -> None:
    units = []
    for pair in PAIRS:
        for year in range(2019, 2024):
            for month in range(1, 13):
                units.append({
                    "pair": pair,
                    "year": year,
                    "month": month,
                    "expected_category": "Generic ASCII / Tick Data",
                    "expected_archive_pattern": f"HISTDATA_COM_ASCII_{pair}_T{year}{month:02d}.zip (verify browser filename)",
                    "destination_directory": f"data/ticks/inbox/histdata/{pair}/{year}/{month:02d}",
                    "status": "PILOT_REQUIRED" if (pair, year, month) == ("EURUSD", 2019, 1) else "WAIT_FOR_PILOT",
                })
    document = {"schema_version": 1, "units": units, "unit_count": len(units)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
