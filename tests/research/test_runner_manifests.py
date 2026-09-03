from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from mt5_scalping_agent.backtesting import BacktestConfig, BacktestResult
from mt5_scalping_agent.risk import RiskLimits, SymbolRiskSpec
from mt5_scalping_agent.strategies import TrendScalperConfig
from scripts import backtest_trend_scalper, research_backtest, run_experiments, run_london_range_breakout


def _ohlcv(start: str, periods: int, frequency: str = "min") -> pd.DataFrame:
    close = [1.1 + index * 0.00001 for index in range(periods)]
    return pd.DataFrame(
        {
            "time": pd.date_range(start, periods=periods, freq=frequency, tz="UTC"),
            "open": close,
            "high": [value + 0.0001 for value in close],
            "low": [value - 0.0001 for value in close],
            "close": close,
            "tick_volume": [10] * periods,
        }
    )


def _symbol() -> SymbolRiskSpec:
    return SymbolRiskSpec(
        symbol="EURUSD",
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )


def test_all_report_writers_embed_and_write_the_same_manifest(tmp_path: Path) -> None:
    manifest = {"run_id": "test:123", "compatibility_hash": "sha256:123"}
    result = BacktestResult((), (), pd.DataFrame())
    config = BacktestConfig(initial_balance=10_000)
    start = datetime(2026, 1, 5, tzinfo=UTC)
    end = datetime(2026, 1, 6, tzinfo=UTC)

    experiment_report = run_experiments._write_report(
        tmp_path, "EURUSD", start.isoformat(), end.isoformat(), config, [], "test", manifest
    )
    research_report = research_backtest._write_report(
        tmp_path, "EURUSD", start, end, config, result, manifest
    )
    latest_report = backtest_trend_scalper._write_report(
        tmp_path, "EURUSD", result, manifest, _ohlcv("2026-01-05", 40)
    )

    for report_path in (experiment_report, research_report, latest_report):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        manifest_path = Path(report["manifest_path"])
        assert report["run_manifest"] == manifest
        assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest


def test_experiment_manifest_freezes_selected_configuration_and_archive_hash(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    archive_root = tmp_path / "data"
    annual = archive_root / "dukascopy_annual" / "EURUSD_m1_2025.csv.gz"
    annual.parent.mkdir(parents=True)
    annual.write_bytes(b"annual source bytes")
    args = run_experiments.parse_arguments(
        [
            "--start", "2025-01-06T00:00:00Z",
            "--end", "2025-01-07T00:00:00Z",
            "--archive-root", str(archive_root),
            "--experiments", "baseline",
        ]
    )
    experiment = (run_experiments.candidate_configurations()[0],)
    manifest = run_experiments._build_manifest(
        args,
        datetime(2025, 1, 6, tzinfo=UTC),
        datetime(2025, 1, 7, tzinfo=UTC),
        BacktestConfig(initial_balance=10_000, spread_points=1, slippage_points=0.5),
        RiskLimits(),
        _symbol(),
        experiment,
        "local dukascopy archive",
        _ohlcv("2025-01-06", 2),
        _ohlcv("2025-01-06", 2, "5min"),
    )

    strategy = manifest["frozen"]["strategies"][0]
    files = manifest["frozen"]["dataset"]["provider_segments"][0]["files"]
    assert strategy["strategy_name"] == "baseline"
    assert strategy["parameters"] == experiment[0].strategy_config.model_dump(mode="json")
    assert files[0]["sha256"].startswith("sha256:")


def test_mt5_research_manifest_hashes_exact_m1_and_m5_snapshots(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    m1 = _ohlcv("2026-01-05", 40)
    m5 = _ohlcv("2026-01-05", 40, "5min")
    manifest = research_backtest._build_manifest(
        "EURUSD",
        datetime(2026, 1, 5, tzinfo=UTC),
        datetime(2026, 1, 6, tzinfo=UTC),
        BacktestConfig(initial_balance=10_000),
        RiskLimits(),
        _symbol(),
        TrendScalperConfig(),
        "MT5 test terminal (build 1)",
        m1,
        m5,
    )

    snapshots = manifest["frozen"]["dataset"]["content_snapshots"]
    assert [snapshot["name"] for snapshot in snapshots] == ["M1", "M5"]
    assert all(snapshot["sha256"].startswith("sha256:") for snapshot in snapshots)


def test_fixed_rule_runner_writes_manifest_without_running_a_real_backtest(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    annual = tmp_path / "data" / "dukascopy_annual" / "EURUSD_m1_2023.csv.gz"
    annual.parent.mkdir(parents=True)
    annual.write_bytes(b"annual source bytes")

    class FakeArchive:
        def __init__(self, root: Path) -> None:
            self.root = root

        @staticmethod
        def source_for_range(start: datetime, end: datetime) -> str:
            return "dukascopy"

        @staticmethod
        def load_m1(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
            return _ohlcv("2023-01-02", 4)

    class FakeBacktester:
        def __init__(self, *args: object) -> None:
            pass

        @staticmethod
        def run(candles: pd.DataFrame, strategy: object) -> BacktestResult:
            return BacktestResult((), (), pd.DataFrame())

    monkeypatch.setattr(run_london_range_breakout, "LocalResearchArchive", FakeArchive)
    monkeypatch.setattr(run_london_range_breakout, "CandleBacktester", FakeBacktester)
    report_dir = tmp_path / "reports"

    assert run_london_range_breakout.main(
        [
            "--start", "2023-01-02T00:00:00Z",
            "--end", "2023-01-03T00:00:00Z",
            "--strategy", "bollinger_mean_reversion",
            "--report-dir", str(report_dir),
        ]
    ) == 0

    report_path = report_dir / "EURUSD_20230102_20230103_bollinger_mean_reversion.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_manifest"]["experiments"][0]["strategy_name"] == "bollinger_mean_reversion"
    assert Path(report["manifest_path"]).exists()


def test_latest_bars_runner_emits_manifest_report_with_read_only_fakes(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    m1 = _ohlcv("2026-01-05", 40)
    m5 = _ohlcv("2026-01-05", 40, "5min")

    class FakeClient:
        def __init__(self, *args: object) -> None:
            pass

        @staticmethod
        def connect() -> SimpleNamespace:
            return SimpleNamespace(connected=True, terminal_name="test", terminal_version="1")

        @staticmethod
        def select_symbol(symbol: str) -> None:
            pass

        @staticmethod
        def symbol_information(symbol: str) -> dict[str, float]:
            return {
                "point": 0.00001,
                "trade_tick_size": 0.00001,
                "trade_tick_value": 1.0,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
            }

        @staticmethod
        def historical_ohlcv(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
            return m1 if timeframe == backtest_trend_scalper.mt5.TIMEFRAME_M1 else m5

        @staticmethod
        def disconnect() -> None:
            pass

    class FakeBacktester:
        def __init__(self, *args: object) -> None:
            pass

        @staticmethod
        def run(candles: pd.DataFrame, strategy: object) -> BacktestResult:
            return BacktestResult((), (), pd.DataFrame())

    monkeypatch.setattr(backtest_trend_scalper, "MT5ReadOnlyClient", FakeClient)
    monkeypatch.setattr(backtest_trend_scalper, "CandleBacktester", FakeBacktester)
    monkeypatch.setattr(backtest_trend_scalper, "load_settings", lambda: object())
    report_dir = tmp_path / "reports"

    assert backtest_trend_scalper.main(
        ["--m1-bars", "40", "--m5-bars", "40", "--report-dir", str(report_dir)]
    ) == 0

    report_path = next(path for path in report_dir.glob("*_latest_trend_scalper.json") if ".manifest." not in path.name)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_manifest"]["frozen"]["dataset"]["content_snapshots"][0]["row_count"] == 40
    assert Path(report["manifest_path"]).exists()