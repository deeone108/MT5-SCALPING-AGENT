from pathlib import Path

import pandas as pd
import pytest

from mt5_scalping_agent.data.jforex_year_batch import (
    month_bounds,
    partition_year_ticks,
    routed_months,
    validate_batch_directory,
)


def test_month_rotation_boundaries_preserve_every_tick_and_field() -> None:
    times = pd.to_datetime(["2019-01-31T23:59:59.999Z", "2019-02-01T00:00:00.000Z"])
    source = pd.DataFrame({"timestamp_utc_ms": times.astype("int64") // 1_000_000,
                           "bid": [1.1, 1.2], "ask": [1.11, 1.21],
                           "bid_volume": [2.0, 3.0], "ask_volume": [4.0, 5.0],
                           "source_sequence": [8, 9]})
    months = partition_year_ticks(source, 2019)
    assert months[1][["bid", "ask", "bid_volume", "ask_volume"]].values.tolist() == [[1.1, 1.11, 2.0, 4.0]]
    assert months[2][["bid", "ask", "bid_volume", "ask_volume"]].values.tolist() == [[1.2, 1.21, 3.0, 5.0]]
    assert months[1].source_sequence.tolist() == [0]
    assert months[2].source_sequence.tolist() == [0]
    assert sum(map(len, months.values())) == len(source)


def test_leap_february_and_december_year_boundary_are_exact() -> None:
    feb_start, feb_end = month_bounds(2020, 2)
    dec_start, dec_end = month_bounds(2020, 12)
    assert (feb_start.isoformat(), feb_end.isoformat()) == ("2020-02-01T00:00:00+00:00", "2020-03-01T00:00:00+00:00")
    assert (dec_start.isoformat(), dec_end.isoformat()) == ("2020-12-01T00:00:00+00:00", "2021-01-01T00:00:00+00:00")


@pytest.mark.parametrize(
    ("protected", "expected"),
    [
        ({1}, [2, 3]),
        ({1, 2}, [3]),
        ({6}, [1, 2, 3]),
        (set(), [1, 2, 3]),
        (set(range(1, 13)), []),
    ],
)
def test_protected_month_never_terminates_later_routing(protected: set[int], expected: list[int]) -> None:
    assert routed_months([1, 2, 3], protected) == expected


def test_batch_directory_must_be_absolute_existing_and_writable(tmp_path: Path) -> None:
    assert validate_batch_directory(tmp_path) == tmp_path.resolve()
    with pytest.raises(ValueError, match="absolute"):
        validate_batch_directory(Path("data/ticks/incoming/jforex"))
    with pytest.raises(FileNotFoundError):
        validate_batch_directory(tmp_path / "missing")