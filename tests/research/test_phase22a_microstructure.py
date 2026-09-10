import numpy as np
import pandas as pd
import pytest

from scripts.run_phase22a_inference import confidence_interval_excludes_zero, json_default

from mt5_scalping_agent.research.phase22a_microstructure import (
    apply_frozen_bins,
    assert_dataset_root,
    benjamini_hochberg,
    block_bootstrap,
    build_anchor_table,
    pip_size,
    quantile_boundaries,
    temporal_partition,
)


def ticks(start: str, seconds: int = 90) -> pd.DataFrame:
    base = pd.Timestamp(start).value
    times = base + np.arange(seconds * 10, dtype="int64") * 100_000_000
    mid = 1.1 + np.sin(np.arange(len(times)) / 10) * 0.0001
    return pd.DataFrame({"timestamp_utc_ns": times, "bid": mid - 0.00005, "ask": mid + 0.00005})


def test_anchor_freshness_causality_and_future_lookup() -> None:
    frame = ticks("2020-01-02T00:00:00Z")
    start = pd.Timestamp("2020-01-02T00:00:10Z")
    end = pd.Timestamp("2020-01-02T00:01:00Z")
    original = build_anchor_table(frame, "EURUSD", start, end)
    changed = frame.copy()
    changed.loc[changed.timestamp_utc_ns > pd.Timestamp("2020-01-02T00:00:30Z").value, ["bid", "ask"]] += 1
    rerun = build_anchor_table(changed, "EURUSD", start, end)
    row = original.anchor_utc_ns == pd.Timestamp("2020-01-02T00:00:30Z").value
    cols = ["qdi_1s", "qdi_5s", "impulse_15s_pips", "activity_5s", "volatility_15s"]
    pd.testing.assert_frame_equal(original.loc[row, cols], rerun.loc[row, cols])
    assert (original.quote_utc_ns <= original.anchor_utc_ns).all()
    assert (original.quote_age_ns <= 2_000_000_000).all()
    valid = original["future_age_15s_ns"].notna()
    assert (original.loc[valid, "future_age_15s_ns"] <= 2_000_000_000).all()


def test_stale_quotes_make_anchors_ineligible() -> None:
    frame = ticks("2020-01-02T00:00:00Z", seconds=1)
    out = build_anchor_table(frame, "EURUSD", pd.Timestamp("2020-01-02T00:00:10Z"), pd.Timestamp("2020-01-02T00:00:20Z"))
    assert out.empty


def test_spread_conversion_temporal_partitions_and_root_pin() -> None:
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01
    assert [temporal_partition(y) for y in range(2019, 2024)] == ["DISCOVERY"] * 3 + ["CONFIRMATION", "INTERNAL_HOLDOUT"]
    with pytest.raises(ValueError):
        temporal_partition(2024)
    assert_dataset_root("abc", "abc")
    with pytest.raises(ValueError, match="root mismatch"):
        assert_dataset_root("bad", "abc")


def test_discovery_quantiles_are_frozen_for_later_values() -> None:
    boundaries = quantile_boundaries(np.arange(100, dtype=float))
    frozen = list(boundaries)
    assert apply_frozen_bins(np.array([-1.0, 50.0, 200.0]), boundaries).tolist() == [1, 3, 5]
    assert boundaries == frozen


def test_bootstrap_and_fdr_are_deterministic() -> None:
    daily = np.arange(1, 21, dtype=float)
    assert block_bootstrap(daily) == block_bootstrap(daily)
    accepted = benjamini_hochberg({"a": 0.001, "b": 0.02, "c": 0.9})
    assert accepted == {"a": True, "b": True, "c": False}
    assert benjamini_hochberg({"a": 0.8, "b": 0.9}) == {"a": False, "b": False}

def test_missing_bootstrap_interval_fails_discovery_gate_closed() -> None:
    assert not confidence_interval_excludes_zero({"ci_low": None, "ci_high": None})
    assert confidence_interval_excludes_zero({"ci_low": 0.1, "ci_high": 0.2})
    assert confidence_interval_excludes_zero({"ci_low": -0.2, "ci_high": -0.1})
    assert not confidence_interval_excludes_zero({"ci_low": -0.1, "ci_high": 0.1})


def test_inference_payload_serializes_numpy_scalars() -> None:
    import json
    assert json.loads(json.dumps({"count": np.int64(3), "effect": np.float64(0.25)}, default=json_default)) == {"count": 3, "effect": 0.25}


def test_frozen_candidate_registry_is_unchanged() -> None:
    from scripts.run_phase22a_inference import candidates
    registry = candidates()
    assert len(registry) == 85
    assert {c["h"] for c in registry} == {1, 5, 15, 30, 60}
