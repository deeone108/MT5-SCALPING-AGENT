"""Run a fixed chronological robustness comparison for shortlisted strategies."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester, backtest_summary
from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research import (
    build_run_manifest,
    checkpoint_document,
    load_compatible_checkpoint,
    local_archive_dataset,
    write_json_atomic,
)
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec

ALL_STRATEGIES = STRATEGIES


def first_monday(year: int, month: int = 1) -> datetime:
    start = datetime(year, month, 1, tzinfo=UTC)
    return start + timedelta(days=(-start.weekday()) % 7)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run every fixed-rule EURUSD strategy on chronological robustness windows.')
    parser.add_argument('--window-days', type=int, default=28)
    parser.add_argument('--months', type=int, nargs='+', default=(1, 4, 7, 10))
    parser.add_argument('--years', type=int, nargs='+', default=tuple(range(2019, 2027)))
    parser.add_argument('--strategies', nargs='+', choices=tuple(ALL_STRATEGIES), default=tuple(ALL_STRATEGIES))
    parser.add_argument('--spread-points', type=float, default=1.0)
    parser.add_argument('--slippage-points', type=float, default=0.5)
    parser.add_argument('--commission-per-lot', type=float, default=0.0)
    parser.add_argument('--report-path', type=Path, default=Path('reports/chronological_validation/eurusd_2019_2026_all_strategies_four_month_summary.json'))
    parser.add_argument(
        '--restart', action='store_true',
        help='explicitly replace any existing checkpoint instead of attempting a compatible resume',
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.window_days <= 0:
        raise ValueError('--window-days must be positive')
    if any(month < 1 or month > 12 for month in args.months):
        raise ValueError('--months values must be between 1 and 12')
    if len(set(args.months)) != len(args.months) or len(set(args.years)) != len(args.years):
        raise ValueError('--months and --years must not contain duplicates')

    project_root = Path.cwd()
    archive_root = Path('data')
    symbol = SymbolRiskSpec(
        symbol='EURUSD', point=0.00001, tick_size=0.00001, tick_value=1.0,
        volume_min=0.01, volume_max=100, volume_step=0.01,
    )
    config = BacktestConfig(
        initial_balance=10_000,
        spread_points=args.spread_points,
        slippage_points=args.slippage_points,
        commission_per_lot_per_side=args.commission_per_lot,
    )
    risk_limits = RiskLimits()
    archive = LocalResearchArchive(archive_root)
    selected_strategies = {name: ALL_STRATEGIES[name] for name in args.strategies}
    execution_timestamp = datetime.now(UTC)
    windows = _validation_windows(args.years, args.months, args.window_days)
    eligible_windows = [window for window in windows if _window_end(window) <= execution_timestamp]
    dataset = _local_archive_dataset(archive_root, archive, symbol.symbol, eligible_windows, project_root)
    expected_manifest = build_run_manifest(
        run_kind='chronological_validation',
        execution_timestamp=execution_timestamp,
        strategies=selected_strategies,
        symbol=symbol.symbol,
        timeframe='M1',
        periods=_period_manifest(windows, eligible_windows),
        dataset=dataset,
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
        runner_settings={
            'window_rule': 'first Monday of each selected month, fixed consecutive window',
            'window_days': args.window_days,
            'months': list(args.months),
            'years': list(args.years),
            'split_year_maximum_development': 2023,
        },
        relevant_code_objects=(
            BacktestConfig, CandleBacktester, LocalResearchArchive, RiskEngine, RiskLimits, SymbolRiskSpec,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=None,
        project_root=project_root,
    )

    results: list[dict[str, object]] = []
    skipped_windows: list[dict[str, object]] = []
    checkpoint_path = args.report_path.with_suffix('.checkpoint.json')
    manifest_path = args.report_path.with_suffix('.manifest.json')
    checkpoint = None if args.restart else load_compatible_checkpoint(checkpoint_path, expected_manifest)
    if checkpoint is None:
        run_manifest = expected_manifest
        write_json_atomic(checkpoint_path, checkpoint_document(run_manifest, results, skipped_windows))
    else:
        run_manifest = cast(dict[str, object], checkpoint['manifest'])
        results = cast(list[dict[str, object]], checkpoint['results'])
        skipped_windows = cast(list[dict[str, object]], checkpoint['skipped_windows'])
    write_json_atomic(manifest_path, run_manifest)

    data_cutoff = datetime.fromisoformat(str(run_manifest['execution_timestamp']))
    skipped_keys = {(row.get('year'), row.get('month')) for row in skipped_windows}
    for window in windows:
        year, month, split = int(window['year']), int(window['month']), str(window['split'])
        start, end = _window_start(window), _window_end(window)
        completed = {
            row['strategy'] for row in results
            if row['year'] == year and row.get('month', 1) == month
        }
        if completed.issuperset(selected_strategies):
            print(f'Skipping completed window {year}-{month:02d}', flush=True)
            continue
        if end > data_cutoff:
            if (year, month) not in skipped_keys:
                skipped_windows.append({
                    'year': year,
                    'month': month,
                    'start': start.isoformat(),
                    'end': end.isoformat(),
                    'reason': 'window extends beyond frozen run data cutoff',
                })
                skipped_keys.add((year, month))
                write_json_atomic(checkpoint_path, checkpoint_document(run_manifest, results, skipped_windows))
            continue
        candles = archive.load_m1(symbol.symbol, start, end)
        for name, strategy_type in selected_strategies.items():
            result = CandleBacktester(config, RiskEngine(risk_limits), symbol).run(candles, strategy_type())
            results.append({
                'strategy': name,
                'split': split,
                'year': year,
                'month': month,
                'start': start.isoformat(),
                'end': end.isoformat(),
                **backtest_summary(result, symbol=symbol.symbol),
            })
        write_json_atomic(checkpoint_path, checkpoint_document(run_manifest, results, skipped_windows))
        print(f'Completed window {year}-{month:02d}: {len(results)} strategy-window results saved', flush=True)

    aggregates: list[dict[str, object]] = []
    for split in ('development', 'post_selection_holdout'):
        for strategy in selected_strategies:
            rows = [row for row in results if row['split'] == split and row['strategy'] == strategy]
            if not rows:
                continue
            trade_count = sum(int(row['trade_count']) for row in rows)
            gross_pnl = sum(float(row['gross_pnl']) for row in rows)
            net_profit = sum(float(row['net_profit']) for row in rows)
            total_spread_cost = sum(float(row['total_spread_cost']) for row in rows)
            total_slippage_cost = sum(float(row['total_slippage_cost']) for row in rows)
            total_commission = sum(float(row['total_commission']) for row in rows)
            aggregates.append({
                'strategy': strategy,
                'split': split,
                'window_count': len(rows),
                'trade_count': trade_count,
                'total_lots': sum(float(row['total_lots']) for row in rows),
                'gross_pnl': gross_pnl,
                'total_spread_cost': total_spread_cost,
                'total_slippage_cost': total_slippage_cost,
                'total_commission': total_commission,
                'total_transaction_cost': total_spread_cost + total_slippage_cost + total_commission,
                'net_profit': net_profit,
                'gross_expectancy_per_trade': gross_pnl / trade_count if trade_count else None,
                'net_expectancy_per_trade': net_profit / trade_count if trade_count else None,
                'positive_windows': sum(float(row['net_profit']) > 0 for row in rows),
                'worst_window_net_profit': min(float(row['net_profit']) for row in rows),
            })
    report = {
        'purpose': 'post-selection chronological robustness check for every fixed-rule baseline; not a blind holdout because sampled 2024-2026 data was previously reviewed',
        'symbol': symbol.symbol,
        'window_rule': 'first Monday of each selected month, fixed consecutive window',
        'window_days': args.window_days,
        'months': list(args.months),
        'years': list(args.years),
        'strategies': list(selected_strategies),
        'backtest_assumptions': config.model_dump(mode='json'),
        'data_cutoff': data_cutoff.isoformat(),
        'run_manifest': run_manifest,
        'manifest_path': manifest_path.as_posix(),
        'results': results,
        'aggregates': aggregates,
        'skipped_windows': skipped_windows,
    }
    write_json_atomic(args.report_path, report)
    print(f'Report: {args.report_path}')
    for row in aggregates:
        print(f"{row['split']} {row['strategy']}: trades={row['trade_count']} net={row['net_profit']:.2f} positive_windows={row['positive_windows']}/{row['window_count']}")
    return 0


def _validation_windows(
    years: Sequence[int], months: Sequence[int], window_days: int
) -> list[dict[str, object]]:
    return [
        {
            'year': year,
            'month': month,
            'split': 'development' if year <= 2023 else 'post_selection_holdout',
            'start': first_monday(year, month).isoformat(),
            'end': (first_monday(year, month) + timedelta(days=window_days)).isoformat(),
        }
        for year in years
        for month in months
    ]


def _window_start(window: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(window['start']))


def _window_end(window: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(window['end']))


def _period_manifest(
    windows: list[dict[str, object]], eligible_windows: list[dict[str, object]]
) -> dict[str, object]:
    eligible_keys = {(window['year'], window['month']) for window in eligible_windows}
    return {
        'split_rule': 'calendar years through 2023 are development; later years are post-selection holdout',
        'development_windows': [window for window in windows if window['split'] == 'development'],
        'validation_windows': [window for window in windows if window['split'] == 'post_selection_holdout'],
        'eligible_window_keys_at_run_start': [
            {'year': window['year'], 'month': window['month']}
            for window in windows if (window['year'], window['month']) in eligible_keys
        ],
    }


def _local_archive_dataset(
    archive_root: Path,
    archive: LocalResearchArchive,
    symbol: str,
    windows: list[dict[str, object]],
    project_root: Path,
) -> dict[str, object]:
    return local_archive_dataset(
        archive_root=archive_root,
        archive=archive,
        symbol=symbol,
        periods=[(_window_start(window), _window_end(window)) for window in windows],
        project_root=project_root,
    )

if __name__ == '__main__':
    raise SystemExit(main())