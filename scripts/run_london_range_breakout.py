"""Run fixed-rule research baselines on local EURUSD archive data."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, backtest_summary
from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research import build_run_manifest, local_archive_dataset, write_json_atomic
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must include UTC offset')
    return result.astimezone(UTC)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run fixed-rule research on local EURUSD data.')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--balance', type=float, default=10000)
    parser.add_argument('--spread-points', type=float, default=1.0)
    parser.add_argument('--slippage-points', type=float, default=0.5)
    parser.add_argument('--commission-per-lot', type=float, default=0.0)
    parser.add_argument('--report-dir', type=Path, default=Path('reports'))
    parser.add_argument('--strategy', choices=tuple(STRATEGIES), default='london_range_breakout')
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    start, end = parse_time(args.start), parse_time(args.end)
    archive_root = Path('data')
    archive = LocalResearchArchive(archive_root)
    source = archive.source_for_range(start, end)
    m1 = archive.load_m1('EURUSD', start, end)
    symbol = SymbolRiskSpec(
        symbol='EURUSD', point=0.00001, tick_size=0.00001, tick_value=1.0,
        volume_min=0.01, volume_max=100, volume_step=0.01,
    )
    config = BacktestConfig(
        initial_balance=args.balance,
        spread_points=args.spread_points,
        slippage_points=args.slippage_points,
        commission_per_lot_per_side=args.commission_per_lot,
    )
    risk_limits = RiskLimits()
    strategy_type = STRATEGIES[args.strategy]
    result = CandleBacktester(config, RiskEngine(risk_limits), symbol).run(m1, strategy_type())
    manifest = build_run_manifest(
        run_kind='fixed_rule_local_archive_backtest',
        execution_timestamp=datetime.now(UTC),
        strategies={args.strategy: strategy_type},
        symbol=symbol.symbol,
        timeframe='M1',
        periods={
            'designation': 'single ad-hoc research window; no development/validation designation',
            'start': start.isoformat(),
            'end': end.isoformat(),
        },
        dataset=local_archive_dataset(
            archive_root=archive_root,
            archive=archive,
            symbol=symbol.symbol,
            periods=[(start, end)],
            project_root=Path.cwd(),
        ),
        transaction_costs={
            'spread_points': config.spread_points,
            'slippage_points': config.slippage_points,
            'commission_model': {
                'kind': 'fixed_per_lot_per_side',
                'amount': config.commission_per_lot_per_side,
                'currency': 'account_currency',
                'charged_sides': 2,
            },
        },
        starting_equity=config.initial_balance,
        risk_settings=risk_limits.model_dump(mode='json'),
        symbol_settings=symbol.model_dump(mode='json'),
        runner_settings={'data_source': f'local {source} archive'},
        relevant_code_objects=(
            BacktestConfig, CandleBacktester, LocalResearchArchive,
            RiskEngine, RiskLimits, SymbolRiskSpec,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=None,
        project_root=Path.cwd(),
    )
    args.report_dir.mkdir(parents=True, exist_ok=True)
    path = args.report_dir / f'EURUSD_{start:%Y%m%d}_{end:%Y%m%d}_{args.strategy}.json'
    manifest_path = path.with_suffix('.manifest.json')
    summary = {
        'strategy': args.strategy,
        'symbol': symbol.symbol,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'data_source': f'local {source} archive',
        'backtest_assumptions': config.model_dump(mode='json'),
        'run_manifest': manifest,
        'manifest_path': manifest_path.as_posix(),
        **backtest_summary(result, symbol=symbol.symbol),
    }
    write_json_atomic(manifest_path, manifest)
    write_json_atomic(path, summary)
    print(f'Report: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())