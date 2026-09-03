"""Run a read-only historical M1/M5 simulation using data from MT5."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, backtest_summary
from mt5_scalping_agent.backtesting.trend_scalper import TrendScalperBacktestStrategy
from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5DataError, MT5ReadOnlyClient
from mt5_scalping_agent.research import build_run_manifest, fingerprint_dataframe, write_json_atomic
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec
from mt5_scalping_agent.strategies import TrendScalper, TrendScalperConfig

LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a read-only M1/M5 TrendScalper simulation.")
    parser.add_argument("--symbol", default="EURUSD", help="MT5 symbol to simulate")
    parser.add_argument("--m1-bars", type=int, default=2_000, help="Number of M1 candles")
    parser.add_argument("--m5-bars", type=int, default=500, help="Number of M5 candles")
    parser.add_argument("--balance", type=float, default=10_000, help="Starting simulated balance")
    parser.add_argument("--spread-points", type=float, default=1.0, help="Fixed simulated spread")
    parser.add_argument("--slippage-points", type=float, default=0.5, help="Fixed simulated entry slippage")
    parser.add_argument("--commission-per-lot", type=float, default=0.0, help="Commission per lot per side")
    parser.add_argument("--report-dir", type=Path, default=Path("reports"), help="Research report directory")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.m1_bars < 35 or args.m5_bars < 35:
        raise ValueError("--m1-bars and --m5-bars must each be at least 35")

    client = MT5ReadOnlyClient(load_settings(), mt5)
    try:
        status = client.connect()
        if not status.connected:
            raise MT5DataError("MT5 initialized but terminal information is unavailable")
        client.select_symbol(args.symbol)
        metadata = client.symbol_information(args.symbol)
        m1 = client.historical_ohlcv(args.symbol, mt5.TIMEFRAME_M1, args.m1_bars)
        m5 = client.historical_ohlcv(args.symbol, mt5.TIMEFRAME_M5, args.m5_bars)
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
            TrendScalperBacktestStrategy(
                args.symbol, m5, symbol.point, args.spread_points, TrendScalper(strategy_config)
            ),
        )
        terminal_source = f"MT5 {status.terminal_name or 'terminal'} (build {status.terminal_version or 'unknown'})"
        manifest = _build_manifest(
            args, config, risk_limits, symbol, strategy_config, terminal_source, m1, m5
        )
        report_path = _write_report(args.report_dir, args.symbol, result, manifest, m1)
        print(f"Connected to {status.terminal_name or 'MT5'} (build {status.terminal_version or 'unknown'})")
        print(f"Trades: {len(result.trades)}")
        print(f"Rejected intents: {len(result.rejected_intents)}")
        print(f"Gross PnL: {result.gross_pnl:.2f}")
        print(f"Transaction costs: {result.total_transaction_cost:.2f}")
        print(f"Net profit: {result.net_profit:.2f}")
        print(f"Win rate: {'n/a' if result.win_rate is None else f'{result.win_rate:.1%}'}")
        print(f"Profit factor: {'n/a' if result.profit_factor is None else f'{result.profit_factor:.2f}'}")
        print(f"Maximum drawdown: {result.max_drawdown:.2f}")
        print(f"Report: {report_path}")
        return 0
    except (MT5DataError, RuntimeError, KeyError, ValueError) as error:
        LOGGER.error("Historical simulation failed: %s", error)
        return 1
    finally:
        client.disconnect()


def _build_manifest(
    args: argparse.Namespace,
    config: BacktestConfig,
    risk_limits: RiskLimits,
    symbol: SymbolRiskSpec,
    strategy_config: TrendScalperConfig,
    terminal_source: str,
    m1,  # type: ignore[no-untyped-def]
    m5,  # type: ignore[no-untyped-def]
) -> dict[str, object]:
    return build_run_manifest(
        run_kind="mt5_latest_bars_trend_scalper_backtest",
        execution_timestamp=datetime.now(UTC),
        strategies={"trend_scalper": TrendScalper},
        strategy_parameters={"trend_scalper": strategy_config.model_dump(mode="json")},
        symbol=args.symbol,
        timeframe="M1 signals with completed M5 context",
        periods={
            "designation": "latest-bars ad-hoc research snapshot; no development/validation designation",
            "m1": {
                "requested_bars": args.m1_bars,
                "first_timestamp": m1["time"].iloc[0].isoformat(),
                "last_timestamp": m1["time"].iloc[-1].isoformat(),
            },
            "m5": {
                "requested_bars": args.m5_bars,
                "first_timestamp": m5["time"].iloc[0].isoformat(),
                "last_timestamp": m5["time"].iloc[-1].isoformat(),
            },
        },
        dataset={
            "kind": "mt5_latest_bars_api_snapshot",
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
        runner_settings={"m1_bars": args.m1_bars, "m5_bars": args.m5_bars},
        relevant_code_objects=(
            BacktestConfig, CandleBacktester, MT5ReadOnlyClient, RiskEngine, RiskLimits,
            SymbolRiskSpec, TrendScalper, TrendScalperBacktestStrategy, TrendScalperConfig,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=None,
        project_root=Path.cwd(),
    )


def _write_report(report_dir: Path, symbol: str, result, manifest: dict[str, object], m1) -> Path:  # type: ignore[no-untyped-def]
    report_dir.mkdir(parents=True, exist_ok=True)
    start = m1["time"].iloc[0].to_pydatetime()
    end = m1["time"].iloc[-1].to_pydatetime() + timedelta(minutes=1)
    path = report_dir / f"{symbol}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}_latest_trend_scalper.json"
    manifest_path = path.with_suffix(".manifest.json")
    summary = {
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "run_manifest": manifest,
        "manifest_path": manifest_path.as_posix(),
        **backtest_summary(result, symbol=symbol),
    }
    write_json_atomic(manifest_path, manifest)
    write_json_atomic(path, summary)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())