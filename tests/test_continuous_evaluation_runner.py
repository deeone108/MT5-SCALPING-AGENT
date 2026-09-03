import json
from pathlib import Path

import pandas as pd

import pytest

from mt5_scalping_agent.risk import RiskLimits

from scripts.run_continuous_evaluation import (
    _development_dataset,
    NONBINDING_RESEARCH_COUNT,
    _isolated_periods,
    _validate_checkpoint_results,
    main,
    parse_arguments,
    risk_limits_for_profile,
)


def test_runner_has_no_cli_dates_and_freezes_post_selection_out() -> None:
    args = parse_arguments(["--strategies", "new_york_bollinger_rsi_reversal"])
    periods = _isolated_periods()

    assert args.risk_profile == "research_diagnostics"
    assert parse_arguments(["--risk-profile", "deployment_limits"]).risk_profile == "deployment_limits"
    assert not hasattr(args, "start")
    assert not hasattr(args, "end")
    assert periods["development"]["start"] == "2019-01-01T00:00:00+00:00"
    assert periods["development"]["end"] == "2024-01-01T00:00:00+00:00"
    assert periods["post_selection_robustness"]["permitted_for_this_run"] is False


def test_dataset_descriptor_hashes_only_2019_through_2023(tmp_path: Path) -> None:
    archive_root = tmp_path / "data"
    annual = archive_root / "dukascopy_annual"
    annual.mkdir(parents=True)
    for year in range(2019, 2024):
        (annual / f"EURUSD_m1_{year}.csv.gz").write_bytes(str(year).encode())
    # A post-selection file may exist but must never enter this run's identity.
    (annual / "EURUSD_m1_2024.csv.gz").write_bytes(b"post-selection")

    dataset = _development_dataset(archive_root, "EURUSD", tmp_path)

    files = dataset["provider_segments"][0]["files"]
    assert [Path(row["path"]).name for row in files] == [
        f"EURUSD_m1_{year}.csv.gz" for year in range(2019, 2024)
    ]


def test_resume_rejects_a_changed_trade_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text("original", encoding="utf-8")
    row = {
        "strategy": "new_york_reversal",
        "trade_ledger": {
            "path": "ledger.json",
            "sha256": "sha256:not-the-file-hash",
        },
    }

    with pytest.raises(ValueError, match="changed"):
        _validate_checkpoint_results(
            [row], {"new_york_reversal": object}, tmp_path
        )


def test_runner_writes_manifest_checkpoint_summary_and_trade_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_root = tmp_path / "data"
    annual = archive_root / "dukascopy_annual"
    annual.mkdir(parents=True)
    for year in range(2019, 2024):
        times = pd.date_range(f"{year}-01-02T08:00:00Z", periods=6, freq="min")
        frame = pd.DataFrame(
            {
                "time": times,
                "open": [1.1] * 6,
                "high": [1.1002] * 6,
                "low": [1.0998] * 6,
                "close": [1.1] * 6,
                "tick_volume": [10] * 6,
            }
        )
        frame.to_csv(
            annual / f"EURUSD_m1_{year}.csv.gz",
            index=False,
            compression="gzip",
        )
    report_path = tmp_path / "report.json"
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--archive-root",
            str(archive_root),
            "--report-path",
            str(report_path),
            "--strategies",
            "previous_day_range_breakout",
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["risk_profile"] == "research_diagnostics"
    frozen = report["run_manifest"]["frozen"]
    assert frozen["runner_settings"]["risk_profile"] == "research_diagnostics"
    assert frozen["risk_settings"]["max_drawdown_percent"] == 100.0
    assert frozen["risk_settings"]["max_consecutive_losses"] == NONBINDING_RESEARCH_COUNT
    assert report["periods"]["post_selection_robustness"]["permitted_for_this_run"] is False
    assert [row["strategy"] for row in report["results"]] == [
        "previous_day_range_breakout"
    ]
    ledger_path = tmp_path / report["results"][0]["trade_ledger"]["path"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["period"]["post_selection_data_used"] is False
    assert ledger["statistical_robustness"]["sample"]["trade_count"] == 0
    assert report["results"][0]["statistical_robustness"]["sample"]["trade_count"] == 0
    assert ledger["summaries"]["by_month"][0]["group"] == "2019-01"
    assert report_path.with_suffix(".manifest.json").is_file()
    assert report_path.with_suffix(".checkpoint.json").is_file()

def test_risk_profiles_disable_only_research_censoring_limits() -> None:
    defaults = RiskLimits()
    research = risk_limits_for_profile("research_diagnostics")
    deployment = risk_limits_for_profile("deployment_limits")

    assert deployment == defaults
    assert research.max_daily_loss_percent == 100.0
    assert research.max_weekly_loss_percent == 100.0
    assert research.max_drawdown_percent == 100.0
    assert research.max_consecutive_losses == NONBINDING_RESEARCH_COUNT
    assert research.max_trades_per_hour == NONBINDING_RESEARCH_COUNT
    assert research.max_trades_per_day == NONBINDING_RESEARCH_COUNT

    preserved_fields = (
        "risk_percent_per_trade",
        "reset_consecutive_losses_each_utc_day",
        "max_open_positions",
        "max_exposure_lots",
        "max_symbol_exposure_lots",
        "max_lot_size",
        "min_reward_risk_ratio",
        "max_spread_points",
        "max_market_data_age_seconds",
    )
    for field in preserved_fields:
        assert getattr(research, field) == getattr(defaults, field)

    with pytest.raises(ValueError, match="unknown risk profile"):
        risk_limits_for_profile("not_a_profile")