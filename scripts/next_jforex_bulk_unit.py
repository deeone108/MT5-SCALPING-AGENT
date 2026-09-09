"""Print the next pending JForex unit as copy-ready Strategy Tester parameters."""

import json
from pathlib import Path

from mt5_scalping_agent.data.jforex_bulk import MANIFEST_PATH

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
unit = next((item for item in manifest["units"] if item["status"] in {"PENDING", "FAILED"}), None)
if unit is None:
    print("No pending JForex export units.")
else:
    landing = Path(unit["landing_path"]).resolve()
    print(f"Instrument: {unit['pair'][:3]}/{unit['pair'][3:]}")
    print(f"Start UTC inclusive: {unit['start_utc'].replace('T', ' ').replace('Z', '.000')}")
    print(f"End UTC exclusive: {unit['end_utc'].replace('T', ' ').replace('Z', '.000')}")
    print(f"Output CSV: {landing}")
