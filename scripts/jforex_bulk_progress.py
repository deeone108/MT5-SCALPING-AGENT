"""Show concise Phase 22 JForex unit totals and pair/year progress."""

import json

from mt5_scalping_agent.data.jforex_bulk import MANIFEST_PATH

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
statuses = ("VALIDATED", "PENDING", "FAILED")
print(f"TOTAL UNITS: {len(manifest['units'])}")
for status in statuses:
    print(f"{status}: {sum(unit['status'] == status for unit in manifest['units'])}")
for pair in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD"):
    for year in range(2019, 2024):
        units = [unit for unit in manifest["units"] if unit["pair"] == pair and unit["year"] == year]
        counts = " ".join(f"{status}={sum(unit['status'] == status for unit in units)}" for status in statuses)
        print(f"{pair} {year}: {counts}")
