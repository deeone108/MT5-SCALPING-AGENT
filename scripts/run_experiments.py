"""Run comparable TrendScalper research experiments on archive or MT5 data."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from mt5_scalping_agent.backtesting import BacktestConfig, BacktestResult, BacktestTrade, CandleBacktester, backtest_summary
from mt5_scalping_agent.backtesting.efficient_trend_scalper import EfficientTrendScalperBacktestStrategy
from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import LocalArchiveError, LocalResearchArchive, MT5DataError, TickAnalysisError, analyze_tick_spreads, resample_m1_to_m5
from mt5_scalping_agent.data.historical_range import MT5HistoricalRangeClient
from mt5_scalping_agent.research import (
    build_run_manifest,
    fingerprint_dataframe,
    fingerprint_files,
    local_archive_dataset,
    write_json_atomic,
)
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec
from mt5_scalping_agent.strategies import TrendScalper, TrendScalperConfig

LOGGER = logging.getLogger(__name__)


def parse_utc_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset or Z suffix")
    return timestamp.astimezone(UTC)


@dataclass(frozen=True)
class Experiment:
    name: str
    strategy_config: TrendScalperConfig


def candidate_configurations() -> tuple[Experiment, ...]:
    """Return small, interpretable variants for fixed-window comparison."""
    return (
        Experiment("baseline", TrendScalperConfig()),
        Experiment("london_morning", TrendScalperConfig(session_start_utc=time(7), session_end_utc=time(12))),
        Experiment("strict_rsi", TrendScalperConfig(buy_rsi_minimum=55, buy_rsi_maximum=65, sell_rsi_minimum=35, sell_rsi_maximum=45)),
        Experiment("tight_spread", TrendScalperConfig(max_spread_points=1.5)),
        Experiment("m5_trend_strength", TrendScalperConfig(min_m5_trend_strength=0.15)),
        Experiment("m1_volatility", TrendScalperConfig(min_m1_atr_fraction=0.000058)),
        Experiment("m1_pullback", TrendScalperConfig(require_m1_pullback=True)),
        Experiment("wider_target", TrendScalperConfig(take_profit_atr_multiple=2.5)),
    )


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare fixed TrendScalper candidates on one historical period.")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", required=True, help="Inclusive UTC ISO timestamp")
    parser.add_argument("--end", required=True, help="Exclusive UTC ISO timestamp")
    parser.add_argument("--balance", type=float, default=10_000)
    parser.add_argument("--spread-points", type=float, default=1.0)
    parser.add_argument("--tick-spread-csv", type=Path)
    parser.add_argument("--tick-spread-statistic", choices=("median", "p95"), default="p95")
    parser.add_argument("--slippage-points", type=float, default=0.5)
    parser.add_argument("--commission-per-lot", type=float, default=0.0)
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--data-source", choices=("archive", "mt5"), default="archive")
    parser.add_argument("--archive-root", type=Path, default=Path("data"))
    parser.add_argument("--point", type=float, default=0.00001)
    parser.add_argument("--tick-size", type=float, default=0.00001)
    parser.add_argument("--tick-value", type=float, default=1.0)
    parser.add_argument("--volume-min", type=float, default=0.01)
    parser.add_argument("--volume-max", type=float, default=100.0)
    parser.add_argument("--volume-step", type=float, default=0.01)
    parser.add_argument("--experiments", nargs="+", choices=[candidate.name for candidate in candidate_configurations()])
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    start, end = parse_utc_timestamp(args.start), parse_utc_timestamp(args.end)
    client = MT5HistoricalRangeClient(load_settings(), mt5) if args.data_source == "mt5" else None
    try:
        spread_points = _resolve_spread_points(args)
        m1, m5, symbol, source_description = _load_market_data(args, start, end, client)
        backtest_config = BacktestConfig(
            initial_balance=args.balance,
            spread_points=spread_points,
            slippage_points=args.slippage_points,
            commission_per_lot_per_side=args.commission_per_lot,
        )
        risk_limits = RiskLimits()
        results = []
        experiments = candidate_configurations()
        if args.experiments:
            selected_names = set(args.experiments)
            experiments = tuple(candidate for candidate in experiments if candidate.name in selected_names)
        for experiment in experiments:
            strategy = EfficientTrendScalperBacktestStrategy(
                args.symbol, m1, m5, symbol.point, spread_points, TrendScalper(experiment.strategy_config)
            )
            result = CandleBacktester(backtest_config, RiskEngine(risk_limits), symbol).run(m1, strategy)
            results.append(
                {
                    "name": experiment.name,
                    "strategy_config": experiment.strategy_config.model_dump(mode="json"),
                    **backtest_summary(result, symbol=args.symbol),
                    "diagnostics": _trade_diagnostics(result),
                }
            )
        manifest = _build_manifest(
            args, start, end, backtest_config, risk_limits, symbol, experiments,
            source_description, m1, m5,
        )
        report_path = _write_report(
            args.report_dir, args.symbol, start.isoformat(), end.isoformat(), backtest_config,
            results, source_description, manifest,
        )
        print(f"Data source: {source_description}")
        for result in results:
            print(f"{result['name']}: trades={result['trade_count']}, net_profit={result['net_profit']:.2f}, profit_factor={result['profit_factor']}")
        print(f"Report: {report_path}")
        return 0
    except (LocalArchiveError, MT5DataError, RuntimeError, KeyError, ValueError) as error:
        LOGGER.error("Experiment run failed: %s", error)
        return 1
    finally:
        if client is not None:
            client.disconnect()


def _resolve_spread_points(args: argparse.Namespace) -> float:
    if args.tick_spread_csv is None:
        return args.spread_points
    try:
        analysis = analyze_tick_spreads(args.tick_spread_csv)
    except (TickAnalysisError, ValueError) as error:
        raise ValueError(f"tick spread calibration failed: {error}") from error
    summary = analysis["spread_points_fresh"]
    spread = summary[args.tick_spread_statistic]
    if spread is None:
        raise ValueError("tick spread calibration has no fresh records")
    return float(spread)


def _trade_diagnostics(result: BacktestResult) -> dict[str, object]:
    """Summarize completed trades for structural research without rewriting trade data."""
    trades = result.trades
    if not trades:
        return {"average_holding_minutes": None, "by_entry_hour_utc": [], "by_direction": [], "by_exit_reason": []}

    def summarize(grouped: dict[str, list[BacktestTrade]]) -> list[dict[str, object]]:
        return [
            {
                "group": key,
                "trade_count": len(group),
                "net_profit": sum(trade.net_pnl for trade in group),
                "win_rate": sum(trade.net_pnl > 0 for trade in group) / len(group),
            }
            for key, group in sorted(grouped.items())
        ]

    by_hour: dict[str, list[BacktestTrade]] = {}
    by_direction: dict[str, list[BacktestTrade]] = {}
    by_exit_reason: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        by_hour.setdefault(f"{trade.entry_time.hour:02d}", []).append(trade)
        by_direction.setdefault(trade.direction.value, []).append(trade)
        by_exit_reason.setdefault(trade.exit_reason, []).append(trade)
    return {
        "average_holding_minutes": sum((trade.exit_time - trade.entry_time).total_seconds() / 60 for trade in trades) / len(trades),
        "by_entry_hour_utc": summarize(by_hour),
        "by_direction": summarize(by_direction),
        "by_exit_reason": summarize(by_exit_reason),
    }


def _load_market_data(
    args: argparse.Namespace, start: datetime, end: datetime, client: MT5HistoricalRangeClient | None
) -> tuple[pd.DataFrame, pd.DataFrame, SymbolRiskSpec, str]:
    if args.data_source == "archive":
        archive = LocalResearchArchive(args.archive_root)
        source = archive.source_for_range(start, end)
        m1 = archive.load_m1(args.symbol, start, end)
        return (
            m1,
            resample_m1_to_m5(m1),
            SymbolRiskSpec(
                symbol=args.symbol, point=args.point, tick_size=args.tick_size, tick_value=args.tick_value,
                volume_min=args.volume_min, volume_max=args.volume_max, volume_step=args.volume_step,
            ),
            f"local {source} archive",
        )
    if client is None:
        raise RuntimeError("MT5 client was not initialized")
    status = client.connect()
    if not status.connected:
        raise MT5DataError("MT5 initialized but terminal information is unavailable")
    client.select_symbol(args.symbol)
    metadata = client.symbol_information(args.symbol)
    return (
        client.historical_ohlcv_range(args.symbol, mt5.TIMEFRAME_M1, start, end),
        client.historical_ohlcv_range(args.symbol, mt5.TIMEFRAME_M5, start, end),
        SymbolRiskSpec(
            symbol=args.symbol, point=float(metadata["point"]), tick_size=float(metadata["trade_tick_size"]),
            tick_value=float(metadata["trade_tick_value"]), volume_min=float(metadata["volume_min"]),
            volume_max=float(metadata["volume_max"]), volume_step=float(metadata["volume_step"]),
        ),
        f"MT5 {status.terminal_name or 'terminal'} (build {status.terminal_version or 'unknown'})",
    )


def _build_manifest(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    backtest_config: BacktestConfig,
    risk_limits: RiskLimits,
    symbol: SymbolRiskSpec,
    experiments: tuple[Experiment, ...],
    source_description: str,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
) -> dict[str, object]:
    if args.data_source == "archive":
        archive = LocalResearchArchive(args.archive_root)
        dataset = local_archive_dataset(
            archive_root=args.archive_root,
            archive=archive,
            symbol=args.symbol,
            periods=[(start, end)],
            project_root=Path.cwd(),
        )
        dataset["selected_content"] = [fingerprint_dataframe(m1, "M1")]
    else:
        snapshots = [fingerprint_dataframe(m1, "M1"), fingerprint_dataframe(m5, "M5")]
        dataset = {
            "kind": "mt5_historical_api_snapshot",
            "source": source_description,
            "files": [],
            "content_snapshots": snapshots,
        }
    transaction_costs: dict[str, object] = {
        "spread_points": backtest_config.spread_points,
        "slippage_points": backtest_config.slippage_points,
        "commission_model": {
            "kind": "fixed_per_lot_per_side",
            "amount": backtest_config.commission_per_lot_per_side,
            "currency": "account_currency",
            "charged_sides": 2,
        },
    }
    if args.tick_spread_csv is not None:
        transaction_costs["spread_calibration"] = {
            "statistic": args.tick_spread_statistic,
            "files": fingerprint_files([args.tick_spread_csv], Path.cwd()),
        }
    return build_run_manifest(
        run_kind="trend_scalper_experiment_comparison",
        execution_timestamp=datetime.now(UTC),
        strategies={experiment.name: TrendScalper for experiment in experiments},
        strategy_parameters={
            experiment.name: experiment.strategy_config.model_dump(mode="json") for experiment in experiments
        },
        symbol=args.symbol,
        timeframe="M1 signals with completed M5 context",
        periods={
            "designation": "single ad-hoc research window; no development/validation designation",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        dataset=dataset,
        transaction_costs=transaction_costs,
        starting_equity=backtest_config.initial_balance,
        risk_settings=risk_limits.model_dump(mode="json"),
        symbol_settings=symbol.model_dump(mode="json"),
        runner_settings={
            "data_source": args.data_source,
            "selected_experiments": [experiment.name for experiment in experiments],
        },
        relevant_code_objects=(
            BacktestConfig, CandleBacktester, EfficientTrendScalperBacktestStrategy,
            LocalResearchArchive, MT5HistoricalRangeClient, RiskEngine, RiskLimits,
            SymbolRiskSpec, TrendScalper, TrendScalperConfig,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=None,
        project_root=Path.cwd(),
    )


def _write_report(
    report_dir: Path,
    symbol: str,
    start: str,
    end: str,
    backtest_config: BacktestConfig,
    results: list[dict[str, object]],
    data_source: str,
    run_manifest: dict[str, object],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{symbol}_{start[:10].replace('-', '')}_{end[:10].replace('-', '')}_experiments.json"
    manifest_path = path.with_suffix(".manifest.json")
    summary = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "data_source": data_source,
        "backtest_assumptions": backtest_config.model_dump(mode="json"),
        "run_manifest": run_manifest,
        "manifest_path": manifest_path.as_posix(),
        "experiments": results,
    }
    write_json_atomic(manifest_path, run_manifest)
    write_json_atomic(path, summary)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())