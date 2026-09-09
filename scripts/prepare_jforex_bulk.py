"""Create the frozen 240-unit monthly JForex export manifest."""

from mt5_scalping_agent.data.jforex_bulk import MANIFEST_PATH, build_manifest

manifest = build_manifest()
print(f"{MANIFEST_PATH}: {manifest['expected_units']} PENDING units")
