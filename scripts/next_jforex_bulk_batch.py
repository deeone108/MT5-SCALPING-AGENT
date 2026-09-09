"""Print the next copy-ready one-pair/year JForex YEAR_BATCH action."""

import json
from pathlib import Path

from mt5_scalping_agent.data.jforex_bulk import MANIFEST_PATH

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
groups = [(pair, year) for pair in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD") for year in range(2019, 2024)]
for pair, year in groups:
    units = [unit for unit in manifest["units"] if unit["pair"] == pair and unit["year"] == year]
    pending = [unit for unit in units if unit["status"] != "VALIDATED"]
    if pending:
        validated = [str(unit["month"]) for unit in units if unit["status"] == "VALIDATED"]
        print(f"Instrument: {pair[:3]}/{pair[3:]}")
        print(f"Tester start: {year}-01-01 00:00:00.000")
        print(f"Tester end: {year + 1}-01-01 00:00:00.000")
        print("Mode: YEAR_BATCH")
        print(f"Batch year: {year}")
        print(f"Output directory: {Path('data/ticks/incoming/jforex').resolve()}")
        print(f"Validated months to protect: {','.join(validated)}")
        print(f"Pending monthly units: {len(pending)}")
        break
else:
    print("No pending JForex year batches.")
