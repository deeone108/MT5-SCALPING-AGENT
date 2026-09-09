"""Import and validate the frozen provider-authorized JForex tick pilot."""

import argparse
import json
from pathlib import Path

from mt5_scalping_agent.data.jforex_pilot import PILOT_FILENAME, PILOT_LANDING, validate_jforex_pilot

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("exported_file", nargs="?", type=Path)
parser.add_argument("--pilot", action="store_true", help="import the frozen pilot from its deterministic landing path")
parser.add_argument("--data-root", type=Path, default=Path("data/ticks"))
args = parser.parse_args()
if args.pilot == (args.exported_file is not None):
    parser.error("provide exactly one of exported_file or --pilot")
source = PILOT_LANDING / PILOT_FILENAME if args.pilot else args.exported_file
assert source is not None
print(json.dumps(validate_jforex_pilot(source, args.data_root), indent=2, sort_keys=True))