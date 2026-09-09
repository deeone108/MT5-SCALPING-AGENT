"""Import one manually downloaded HistData Generic ASCII tick ZIP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mt5_scalping_agent.data.histdata_tick_source import HistDataTickSource


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("downloaded_file", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data/ticks"))
    args = parser.parse_args()
    result = HistDataTickSource().import_archive(args.downloaded_file, args.data_root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
