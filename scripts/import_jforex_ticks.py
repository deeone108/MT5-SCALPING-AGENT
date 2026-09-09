"""Import frozen provider-authorized JForex tick exports."""

import argparse
import json
from pathlib import Path

from mt5_scalping_agent.data.jforex_bulk import MANIFEST_PATH, process_bulk
from mt5_scalping_agent.data.jforex_pilot import PILOT_FILENAME, PILOT_LANDING, validate_jforex_pilot

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("exported_file", nargs="?", type=Path)
parser.add_argument("--pilot", action="store_true", help="validate the frozen pilot")
parser.add_argument("--bulk", action="store_true", help="scan and validate files from the frozen bulk manifest")
parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
parser.add_argument("--data-root", type=Path, default=Path("data/ticks"))
args = parser.parse_args()
if sum((args.pilot, args.bulk, args.exported_file is not None)) != 1:
    parser.error("provide exactly one of exported_file, --pilot, or --bulk")
if args.bulk:
    result = process_bulk(args.manifest, args.data_root)
else:
    source = PILOT_LANDING / PILOT_FILENAME if args.pilot else args.exported_file
    assert source is not None
    result = validate_jforex_pilot(source, args.data_root)
print(json.dumps(result, indent=2, sort_keys=True))