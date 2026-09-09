"""Import a provider-authorized JForex historical-tick CSV export."""

import argparse
import json
from pathlib import Path

from mt5_scalping_agent.data.jforex_tick_source import import_jforex_ticks

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("exported_file", type=Path)
parser.add_argument("--data-root", type=Path, default=Path("data/ticks"))
args = parser.parse_args()
print(json.dumps(import_jforex_ticks(args.exported_file, args.data_root), indent=2, sort_keys=True))
