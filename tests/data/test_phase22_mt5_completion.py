import numpy as np

from scripts.validate_phase22_mt5_dataset import classify_gaps, merkle_root


def test_merkle_root_is_order_independent_and_content_sensitive() -> None:
    items = [("b", "2"), ("a", "1")]
    assert merkle_root(items) == merkle_root(list(reversed(items)))
    assert merkle_root(items) != merkle_root([("a", "1"), ("b", "3")])


def test_gap_summary_uses_irregular_event_time_without_synthesis() -> None:
    times_ns = np.array([0, 1_000_000_000, 7_000_000_000, 308_000_000_000], dtype="int64")
    summary = classify_gaps(times_ns)
    assert summary["over_5s"] == 2
    assert summary["over_30s"] == 1
    assert summary["over_60s"] == 1
    assert summary["over_5m"] == 1
    assert summary["maximum_ms"] == 301_000.0