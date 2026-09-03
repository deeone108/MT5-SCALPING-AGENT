"""Create reproducible, read-only MT5 historical backtest reports."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, backtest_summary, trade_record
from mt5_scalping_agent.backtesting.efficient_trend_scalper import EfficientTrendScalperBacktestStrategy
from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError
from mt5_scalping_agent.data.historical_range import MT5HistoricalRangeClient
from mt5_scalping_agent.research import build_run_manifest, fingerprint_dataframe, write_json_atomic
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec
from mt5_scalping_agent.strategies import TrendScalper, TrendScalperConfig

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a fixed-window, read-only MT5 backtest report.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", required=True, help="Inclusive UTC ISO timestamp, for example 2026-08-20T00:00:00Z")
    parser.add_argument("--end", required=True, help="Exclusive UTC ISO timestamp, for example 2026-08-21T00:00:00Z")
    parser.add_argument("--balance", type=float, default=10_000)
    parser.add_argument("--spread-points", type=float, default=1.0)
    parser.add_argument("--slippage-points", type=float, default=0.5)
    parser.add_argument("--commission-per-lot", type=float, default=0.0)
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    return parser.parse_args(arguments)


def parse_utc_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset or Z suffix")
    return timestamp.astimezone(UTC)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    start, end = parse_utc_timestamp(args.start), parse_utc_timestamp(args.end)
    client = MT5HistoricalRangeClient(load_settings(), mt5)
    try:
        status = client.connect()
        if not status.connected:
            raise MT5DataError("MT5 initialized but terminal information is unavailable")
        client.select_symbol(args.symbol)
        metadata = client.symbol_information(args.symbol)
        m1 = client.historical_ohlcv_range(args.symbol, mt5.TIMEFRAME_M1, start, end)
        m5 = client.historical_ohlcv_range(args.symbol, mt5.TIMEFRAME_M5, start, end)
        symbol = SymbolRiskSpec(
            symbol=args.symbol,
            point=float(metadata["point"]),
            tick_size=float(metadata["trade_tick_size"]),
            tick_value=float(metadata["trade_tick_value"]),
            volume_min=float(metadata["volume_min"]),
            volume_max=float(metadata["volume_max"]),
            volume_step=float(metadata["volume_step"]),
        )
        config = BacktestConfig(
            initial_balance=args.balance,
            spread_points=args.spread_points,
            slippage_points=args.slippage_points,
            commission_per_lot_per_side=args.commission_per_lot,
        )
        risk_limits = RiskLimits()
        strategy_config = TrendScalperConfig()
        result = CandleBacktester(config, RiskEngine(risk_limits), symbol).run(
            m1,
            EfficientTrendScalperBacktestStrategy(
                args.symbol, m1, m5, symbol.point, args.spread_points, TrendScalper(strategy_config)
            ),
        )
        terminal_source = f"MT5 {status.terminal_name or 'terminal'} (build {status.terminal_version or 'unknown'})"
        manifest = _build_manifest(
            args.symbol, start, end, config, risk_limits, symbol, strategy_config,
            terminal_source, m1, m5,
        )
        report_path = _write_report(args.report_dir, args.symbol, start, end, config, result, manifest)
        print(f"Connected to {status.terminal_name or 'MT5'} (build {status.terminal_version or 'unknown'})")
        print(f"Historical window: {start.isoformat()} to {end.isoformat()}")
        print(f"Trades: {len(result.trades)}")
        print(f"Net profit: {result.net_profit:.2f}")
        print(f"Profit factor: {'n/a' if result.profit_factor is None else f'{result.profit_factor:.2f}'}")
        print(f"Report: {report_path}")
        return 0
    except (MT5DataError, RuntimeError, KeyError, ValueError) as error:
        LOGGER.error("Research backtest failed: %s", error)
        return 1
    finally:
        client.disconnect()


def _build_manifest(
    symbol_name: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
    risk_limits: RiskLimits,
    symbol: SymbolRiskSpec,
    strategy_config: TrendScalperConfig,
    terminal_source: str,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
) -> dict[str, object]:
    return build_run_manifest(
        run_kind="mt5_fixed_window_research_backtest",
        execution_timestamp=datetime.now(UTC),
        strategies={"trend_scalper": TrendScalper},
        strategy_parameters={"trend_scalper": strategy_config.model_dump(mode="json")},
        symbol=symbol_name,
        timeframe="M1 signals with completed M5 context",
        periods={
            "designation": "single ad-hoc research window; no development/validation designation",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        dataset={
            "kind": "mt5_historical_api_snapshot",
            "source": terminal_source,
            "files": [],
            "content_snapshots": [fingerprint_dataframe(m1, "M1"), fingerprint_dataframe(m5, "M5")],
        },
        transaction_costs={
            "spread_points": config.spread_points,
            "slippage_points": config.slippage_points,
            "commission_model": {
                "kind": "fixed_per_lot_per_side",
                "amount": config.commission_per_lot_per_side,
                "currency": "account_currency",
                "charged_sides": 2,
            },
        },
        starting_equity=config.initial_balance,
        risk_settings=risk_limits.model_dump(mode="json"),
        symbol_settings=symbol.model_dump(mode="json"),
        runner_settings={"data_source": "mt5_historical_range"},
        relevant_code_objects=(
            BacktestConfig, CandleBacktester, EfficientTrendScalperBacktestStrategy,
            MT5HistoricalRangeClient, RiskEngine, RiskLimits, SymbolRiskSpec,
            TrendScalper, TrendScalperConfig,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=None,
        project_root=Path.cwd(),
    )


def _write_report(
    report_dir: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
    result,  # type: ignore[no-untyped-def]
    run_manifest: dict[str, object] | None = None,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}"
    trades = pd.DataFrame([trade_record(trade) for trade in result.trades])
    if not trades.empty:
        for column in ("entry_time", "exit_time"):
            trades[column] = trades[column].map(lambda value: value.isoformat())
    trades.to_csv(report_dir / f"{stem}_trades.csv", index=False)
    summary_path = report_dir / f"{stem}_summary.json"
    summary = {
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "assumptions": config.model_dump(mode="json"),
        **backtest_summary(result, symbol=symbol),
    }
    if run_manifest is not None:
        manifest_path = summary_path.with_suffix(".manifest.json")
        summary["run_manifest"] = run_manifest
        summary["manifest_path"] = manifest_path.as_posix()
        write_json_atomic(manifest_path, run_manifest)
    write_json_atomic(summary_path, summary)
    return summary_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())