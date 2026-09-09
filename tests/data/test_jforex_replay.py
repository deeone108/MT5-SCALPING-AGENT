from pathlib import Path

import pandas as pd

from mt5_scalping_agent.data.jforex_replay import replay_partitions, replay_sha256


def partition(path: Path, timestamps: list[str]) -> Path:
    time = pd.to_datetime(timestamps, utc=True)
    pd.DataFrame({
        "timestamp_utc_ns": time.astype("int64"), "pair": "EURUSD", "bid": 1.1, "ask": 1.2,
        "bid_volume": 1.0, "ask_volume": 2.0, "source_sequence": range(len(time)),
    }).to_parquet(path, index=False)
    return path


def test_cross_month_and_year_replay_is_half_open_and_deterministic(tmp_path: Path) -> None:
    december = partition(tmp_path / "december.parquet", ["2019-12-31T23:59:59.999Z"])
    january = partition(tmp_path / "january.parquet", ["2020-01-01T00:00:00Z", "2020-01-01T00:00:01Z"])
    start, end = pd.Timestamp("2019-12-31T23:59:59Z"), pd.Timestamp("2020-01-01T00:00:01Z")
    first = list(replay_partitions([january, december], start, end))
    second = list(replay_partitions([december, january], start, end))
    assert len(first) == 2
    assert first == second
    assert replay_sha256(first) == replay_sha256(second)
