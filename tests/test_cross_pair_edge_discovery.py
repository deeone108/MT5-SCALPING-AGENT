from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from mt5_scalping_agent.research.cross_pair_edge_discovery import (
    add_pair_features, attach_forward_outcomes, benjamini_hochberg, causal_bars,
    causal_percentile, causal_standardize, day_block_bootstrap_mean, deduplicate_events,
    leave_one_out_factor, opportunity_to_cost, oriented_return, pip_size, structural_events,
)


def _m1(periods=2500):
    times = pd.date_range("2019-01-01", periods=periods, freq="min", tz="UTC")
    close = 1.1 + np.arange(periods) * .00001
    return pd.DataFrame({"time": times, "open": close, "high": close+.00002, "low": close-.00002, "close": close, "tick_volume": 1.0})


@pytest.mark.parametrize(("pair", "expected"), [("EURUSD", .0001), ("GBPUSD", .0001), ("USDJPY", .01), ("USDCAD", .0001)])
def test_pair_pips_and_usd_orientation(pair, expected):
    assert pip_size(pair) == expected
    oriented = oriented_return(pair, pd.Series([.01]))
    assert oriented.iat[0] == pytest.approx(-.01 if pair in {"EURUSD", "GBPUSD"} else .01)


def test_causal_aggregation_discards_incomplete_bucket():
    bars = causal_bars(_m1(16), 5)
    assert len(bars) == 3
    assert bars["completed_time"].iat[0] == pd.Timestamp("2019-01-01 00:04", tz="UTC")


def test_causal_statistics_ignore_future_values():
    values = pd.Series(np.arange(30, dtype=float))
    before = causal_standardize(values, 5).copy(), causal_percentile(values, 5).copy()
    changed = values.copy(); changed.iloc[20:] = 99_999
    after = causal_standardize(changed, 5), causal_percentile(changed, 5)
    pd.testing.assert_series_equal(before[0].iloc[:20], after[0].iloc[:20])
    pd.testing.assert_series_equal(before[1].iloc[:20], after[1].iloc[:20])


def test_leave_one_out_omits_target_and_refuses_missing_component():
    frames = {}
    for pair, value in zip(("EURUSD", "GBPUSD", "USDJPY", "USDCAD"), (1., 2., 3., 4.)):
        frames[pair] = pd.DataFrame({"completed_time": pd.date_range("2019-01-01", periods=2, freq="15min", tz="UTC"), "usd_z": [value, value]})
    frames["USDJPY"].loc[1, "usd_z"] = np.nan
    output = leave_one_out_factor(frames)
    assert output["EURUSD"]["usd_factor"].iat[0] == pytest.approx(3.)
    assert pd.isna(output["EURUSD"]["usd_factor"].iat[1])
    assert output["EURUSD"]["factor_breadth"].iat[0] == 3


def test_structure_is_known_only_after_two_confirmation_bars_and_forward_outcomes():
    m1 = _m1(2600)
    m5, m15 = add_pair_features("EURUSD", m1, volatility_window=20)
    factored = leave_one_out_factor({pair: m15.assign(usd_z=1.0) for pair in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")})["EURUSD"]
    m5.loc[15, "close"] = m5.loc[:14, "high"].max() + .001
    m5.loc[16:17, "close"] = m5.loc[:14, "high"].max() + .001
    events = structural_events("EURUSD", m5, factored)
    assert not events.empty
    event = events.iloc[0]
    assert event.event_time > event.break_time
    outcomes = attach_forward_outcomes(events.head(1), m1, "EURUSD")
    assert "mfe_60m_pips" in outcomes


def test_dedup_ocr_bootstrap_and_fdr_are_deterministic():
    events = pd.DataFrame({"pair": ["EURUSD"]*3, "event_time": pd.to_datetime(["2019-01-01 00:00", "2019-01-01 00:30", "2019-01-02 00:00"], utc=True), "mfe_60m_pips": [4., 8., 12.], "forward_5m_pips": [1., 2., 3.]})
    assert len(deduplicate_events(events)) == 2
    assert opportunity_to_cost(events, 1., 2.)["base"]["threshold_proportions"]["2"] == pytest.approx(1.)
    assert day_block_bootstrap_mean(events, "forward_5m_pips", samples=100, seed=4) == day_block_bootstrap_mean(events, "forward_5m_pips", samples=100, seed=4)
    result = benjamini_hochberg([.01, .04, .5])
    assert result[0]["survives_fdr"] and not result[2]["survives_fdr"]