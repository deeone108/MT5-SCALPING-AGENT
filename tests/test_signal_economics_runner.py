import json
from pathlib import Path

import pandas as pd

from scripts.run_signal_economics import (
    FIXED_VOLUME_LOTS,
    SIGNAL_STRATEGY_NAMES,
    _development_dataset,
    _isolated_periods,
    main,
    parse_arguments,
)


def _write_archive(root: Path) -> None:
    annual = root / "dukascopy_annual"
    annual.mkdir(parents=True)
    for year in range(2019, 2024):
        times = pd.date_range(f"{year}-01-02T12:00:00Z", periods=25, freq="min")
        frame = pd.DataFrame(
            {
                "time": times,
                "open": [1.1] * len(times),
                "high": [1.1001] * len(times),
                "low": [1.0999] * len(times),
                "close": [1.1] * len(times),
                "tick_volume": [10] * len(times),
            }
        )
        frame.to_csv(
            annual / f"EURUSD_m1_{year}.csv.gz",
            index=False,
            compression="gzip",
        )


def test_runner_is_hard_scoped_to_two_strategies_and_development_split() -> None:
    args = parse_arguments([])
    periods = _isolated_periods()

    assert SIGNAL_STRATEGY_NAMES == (
        "new_york_bollinger_rsi_reversal",
        "new_york_reversal",
    )
    assert FIXED_VOLUME_LOTS == 1.0
    assert not hasattr(args, "fixed_volume_lots")
    assert args.spread_points == 2.0
    assert args.slippage_points == 1.0
    assert args.commission_per_lot == 2.0
    assert not hasattr(args, "strategies")
    assert not hasattr(args, "start")
    assert not hasattr(args, "end")
    assert periods["development"]["start"] == "2019-01-01T00:00:00+00:00"
    assert periods["development"]["end"] == "2024-01-01T00:00:00+00:00"
    assert periods["post_selection_robustness"]["permitted_for_this_run"] is False


def test_dataset_descriptor_hashes_only_2019_through_2023(tmp_path: Path) -> None:
    archive = tmp_path / "data"
    _write_archive(archive)
    post_selection = archive / "dukascopy_annual" / "EURUSD_m1_2024.csv.gz"
    post_selection.write_bytes(b"must not be hashed")

    dataset = _development_dataset(archive, "EURUSD", tmp_path)

    files = dataset["provider_segments"][0]["files"]
    assert [Path(item["path"]).name for item in files] == [
        f"EURUSD_m1_{year}.csv.gz" for year in range(2019, 2024)
    ]


def test_runner_writes_compatible_fixed_lot_report_without_strategy_selection(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    archive = tmp_path / "data"
    _write_archive(archive)
    report_path = tmp_path / "reports" / "signal.json"
    monkeypatch.chdir(tmp_path)

    assert main(
        [
            "--archive-root",
            str(archive),
            "--report-path",
            str(report_path),
            "--bootstrap-samples",
            "20",
        ]
    ) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["risk_profile"] == "research_fixed_lot_signal_diagnostics"
    assert report["backtest_assumptions"]["position_sizing_mode"] == "research_fixed_lot"
    assert report["backtest_assumptions"]["fixed_volume_lots"] == 1.0
    assert report["periods"]["post_selection_robustness"]["permitted_for_this_run"] is False
    assert [row["strategy"] for row in report["results"]] == list(
        SIGNAL_STRATEGY_NAMES
    )
    for row in report["results"]:
        assert row["period"]["post_selection_data_used"] is False
        assert row["summaries"]["complete"]["trade_count"] == 0
        assert row["signal_economics"]["complete"]["signal_count"] == 0
        ledger = tmp_path / row["trade_ledger"]["path"]
        assert ledger.is_file()
    assert report_path.with_suffix(".manifest.json").is_file()
    assert report_path.with_suffix(".checkpoint.json").is_file()