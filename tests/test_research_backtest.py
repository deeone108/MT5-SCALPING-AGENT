from datetime import UTC, datetime

import pandas as pd
import pytest

from mt5_scalping_agent.backtesting import BacktestConfig, BacktestResult
from scripts.research_backtest import _write_report, parse_utc_timestamp


def test_parse_utc_timestamp_requires_timezone() -> None:
    assert parse_utc_timestamp("2026-01-05T12:00:00Z") == datetime(2026, 1, 5, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="offset"):
        parse_utc_timestamp("2026-01-05T12:00:00")


def test_write_report_creates_summary_and_empty_trade_csv(tmp_path) -> None:  # type: ignore[no-untyped-def]
    start = datetime(2026, 1, 5, tzinfo=UTC)
    end = datetime(2026, 1, 6, tzinfo=UTC)
    result = BacktestResult((), (), equity_curve=pd.DataFrame())

    summary_path = _write_report(tmp_path, "EURUSD", start, end, BacktestConfig(initial_balance=10_000), result)

    assert summary_path.exists()
    assert '"trade_count": 0' in summary_path.read_text(encoding="utf-8")
    assert (tmp_path / "EURUSD_20260105T0000_20260106T0000_trades.csv").exists()


