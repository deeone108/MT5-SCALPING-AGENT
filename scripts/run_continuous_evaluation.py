"""Run unchanged registered strategies continuously over 2019-2023 development data."""

from __future__ import annotations

import argparse
import gc
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from mt5_scalping_agent.backtesting import BacktestConfig, CandleBacktester
from mt5_scalping_agent.backtesting.strategy_registry import STRATEGIES
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.data.sessions import session_name
from mt5_scalping_agent.research import (
    build_run_manifest,
    checkpoint_document,
    fingerprint_files,
    load_compatible_checkpoint,
    sha256_value,
    write_json_atomic,
)
from mt5_scalping_agent.research.continuous_evaluation import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    POST_SELECTION_START,
    VolatilityRegimeSettings,
    causal_volatility_regimes,
    continuous_result_report,
)
from mt5_scalping_agent.research.statistical_robustness import (
    DEFAULT_BOOTSTRAP_SEED,
    StatisticalRobustnessSettings,
    statistical_robustness_report,
)
from mt5_scalping_agent.risk import RiskEngine, RiskLimits, SymbolRiskSpec


DEFAULT_REPORT_PATH = Path(
    "reports/continuous_evaluation/eurusd_2019_2023_continuous_summary.json"
)


RISK_PROFILES = ("research_diagnostics", "deployment_limits")
NONBINDING_RESEARCH_COUNT = 2_147_483_647


def risk_limits_for_profile(profile: str) -> RiskLimits:
    """Return explicit limits for complete research or deployment-like simulation."""
    defaults = RiskLimits()
    if profile == "deployment_limits":
        return defaults
    if profile == "research_diagnostics":
        return defaults.model_copy(
            update={
                "max_daily_loss_percent": 100.0,
                "max_weekly_loss_percent": 100.0,
                "max_drawdown_percent": 100.0,
                "max_consecutive_losses": NONBINDING_RESEARCH_COUNT,
                "max_trades_per_hour": NONBINDING_RESEARCH_COUNT,
                "max_trades_per_day": NONBINDING_RESEARCH_COUNT,
            }
        )
    raise ValueError(f"unknown risk profile: {profile!r}")


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously evaluate unchanged registered EURUSD strategies on the isolated "
            "2019-2023 development split. This runner cannot load 2024+ data."
        )
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=tuple(STRATEGIES),
        default=tuple(STRATEGIES),
    )
    parser.add_argument("--archive-root", type=Path, default=Path("data"))
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--balance", type=float, default=10_000.0)
    parser.add_argument("--spread-points", type=float, default=2.0)
    parser.add_argument("--slippage-points", type=float, default=1.0)
    parser.add_argument("--commission-per-lot", type=float, default=2.0)
    parser.add_argument(
        "--risk-profile",
        choices=RISK_PROFILES,
        default="research_diagnostics",
        help="research diagnostics disables censoring limits; deployment uses RiskLimits defaults",
    )
    parser.add_argument("--volatility-atr-bars", type=int, default=14)
    parser.add_argument("--volatility-baseline-bars", type=int, default=1_440)
    parser.add_argument("--volatility-minimum-bars", type=int, default=60)
    parser.add_argument("--volatility-low-ratio", type=float, default=0.75)
    parser.add_argument("--volatility-high-ratio", type=float, default=1.50)
    parser.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap-samples", type=int, default=1_000)
    parser.add_argument(
        "--restart",
        action="store_true",
        help="explicitly replace a checkpoint instead of attempting a compatible resume",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    project_root = Path.cwd()
    selected_strategies = {name: STRATEGIES[name] for name in args.strategies}
    volatility_settings = VolatilityRegimeSettings(
        atr_period_bars=args.volatility_atr_bars,
        baseline_window_bars=args.volatility_baseline_bars,
        baseline_minimum_bars=args.volatility_minimum_bars,
        low_ratio_maximum=args.volatility_low_ratio,
        high_ratio_minimum=args.volatility_high_ratio,
    )
    statistical_settings = StatisticalRobustnessSettings(
        random_seed=args.bootstrap_seed,
        bootstrap_samples=args.bootstrap_samples,
    )
    symbol = SymbolRiskSpec(
        symbol="EURUSD",
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    config = BacktestConfig(
        initial_balance=args.balance,
        spread_points=args.spread_points,
        slippage_points=args.slippage_points,
        commission_per_lot_per_side=args.commission_per_lot,
    )
    risk_limits = risk_limits_for_profile(args.risk_profile)
    dataset = _development_dataset(args.archive_root, symbol.symbol, project_root)
    execution_timestamp = datetime.now(UTC)
    expected_manifest = build_run_manifest(
        run_kind="continuous_development_evaluation",
        execution_timestamp=execution_timestamp,
        strategies=selected_strategies,
        symbol=symbol.symbol,
        timeframe="M1",
        periods=_isolated_periods(),
        dataset=dataset,
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
        runner_settings={
            "evaluation_kind": "one continuous backtest per strategy without calendar resets",
            "risk_profile": args.risk_profile,
            "calendar_attribution": "trade_entry_time",
            "calendar_diagnostics": ["complete", "year", "quarter", "month"],
            "categorical_diagnostics": ["direction", "DST-aware session", "causal volatility regime"],
            "volatility_regime": volatility_settings.as_dict(),
            "statistical_robustness": statistical_settings.as_dict(),
            "post_selection_data_access": "forbidden",
        },
        relevant_code_objects=(
            BacktestConfig,
            CandleBacktester,
            LocalResearchArchive,
            RiskEngine,
            RiskLimits,
            SymbolRiskSpec,
            causal_volatility_regimes,
            continuous_result_report,
            session_name,
            statistical_robustness_report,
        ),
        relevant_code_paths=(Path(__file__),),
        random_seed=statistical_settings.random_seed,
        project_root=project_root,
    )

    checkpoint_path = args.report_path.with_suffix(".checkpoint.json")
    manifest_path = args.report_path.with_suffix(".manifest.json")
    checkpoint = (
        None
        if args.restart
        else load_compatible_checkpoint(checkpoint_path, expected_manifest)
    )
    if checkpoint is None:
        run_manifest = expected_manifest
        results: list[dict[str, object]] = []
        write_json_atomic(
            checkpoint_path, checkpoint_document(run_manifest, results, ())
        )
    else:
        run_manifest = cast(dict[str, object], checkpoint["manifest"])
        results = cast(list[dict[str, object]], checkpoint["results"])
        _validate_checkpoint_results(results, selected_strategies, project_root)
    write_json_atomic(manifest_path, run_manifest)

    archive = LocalResearchArchive(args.archive_root)
    print(
        "Loading isolated EURUSD M1 development data: "
        f"{DEVELOPMENT_START.isoformat()} to {DEVELOPMENT_END.isoformat()} (end exclusive)",
        flush=True,
    )
    candles = archive.load_m1(
        symbol.symbol, DEVELOPMENT_START, DEVELOPMENT_END
    )
    volatility = causal_volatility_regimes(candles, volatility_settings)
    completed = {str(row["strategy"]) for row in results}
    total = len(selected_strategies)

    for index, (name, strategy_type) in enumerate(selected_strategies.items(), start=1):
        if name in completed:
            print(f"Skipping completed strategy {index}/{total}: {name}", flush=True)
            continue
        print(
            f"Starting continuous strategy {index}/{total}: {name}. "
            "The checkpoint is saved when this strategy completes.",
            flush=True,
        )
        result = CandleBacktester(
            config, RiskEngine(risk_limits), symbol
        ).run(candles, strategy_type())
        evaluation = continuous_result_report(
            result,
            candles,
            period_start=DEVELOPMENT_START,
            period_end=DEVELOPMENT_END,
            initial_balance=config.initial_balance,
            symbol=symbol.symbol,
            volatility_settings=volatility_settings,
            statistical_settings=statistical_settings,
            precomputed_volatility=volatility,
        )
        detail_path = _detail_path(args.report_path, name)
        detail = {
            "run_id": run_manifest["run_id"],
            "strategy": name,
            "backtest_assumptions": config.model_dump(mode="json"),
            "risk_profile": args.risk_profile,
            **evaluation,
        }
        write_json_atomic(detail_path, detail)
        detail_file = fingerprint_files((detail_path,), project_root)[0]
        summary = cast(dict[str, object], evaluation["summaries"])
        results.append(
            {
                "strategy": name,
                "period": evaluation["period"],
                "attribution_basis": evaluation["attribution_basis"],
                "session_definition": evaluation["session_definition"],
                "volatility_regime_definition": evaluation[
                    "volatility_regime_definition"
                ],
                "summaries": summary,
                "statistical_robustness": evaluation["statistical_robustness"],
                "trade_ledger": detail_file,
            }
        )
        write_json_atomic(
            checkpoint_path, checkpoint_document(run_manifest, results, ())
        )
        complete = cast(dict[str, object], summary["complete"])
        print(
            f"Completed {name}: trades={complete['trade_count']} "
            f"net={float(complete['net_profit']):.2f}; checkpoint saved",
            flush=True,
        )
        del result, evaluation, detail, summary
        gc.collect()

    report = {
        "purpose": (
            "continuous 2019-2023 development diagnostics for unchanged registered "
            "strategies; no 2024-2026 observations are loaded"
        ),
        "symbol": symbol.symbol,
        "periods": _isolated_periods(),
        "backtest_assumptions": config.model_dump(mode="json"),
        "risk_profile": args.risk_profile,
        "run_manifest": run_manifest,
        "manifest_path": manifest_path.as_posix(),
        "results": results,
    }
    write_json_atomic(args.report_path, report)
    print(f"Report: {args.report_path}", flush=True)
    return 0


def _isolated_periods() -> dict[str, object]:
    return {
        "development": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "end_exclusive": True,
        },
        "post_selection_robustness": {
            "start": POST_SELECTION_START.isoformat(),
            "permitted_for_this_run": False,
            "purpose": "preserved for post-selection evidence; never loaded by this runner",
        },
    }


def _development_dataset(
    archive_root: Path, symbol: str, project_root: Path
) -> dict[str, object]:
    paths = tuple(
        archive_root / "dukascopy_annual" / f"{symbol.upper()}_m1_{year}.csv.gz"
        for year in range(DEVELOPMENT_START.year, DEVELOPMENT_END.year)
    )
    files = fingerprint_files(paths, project_root)
    return {
        "kind": "local_annual_m1_ohlcv_archive",
        "archive_root": archive_root.as_posix(),
        "provider_segments": [{"provider": "dukascopy", "files": files}],
        "identifier": sha256_value(files),
    }


def _detail_path(report_path: Path, strategy: str) -> Path:
    directory = report_path.parent / f"{report_path.stem}_details"
    return directory / f"{strategy}.json"


def _validate_checkpoint_results(
    results: Sequence[Mapping[str, object]],
    selected_strategies: Mapping[str, type[object]],
    project_root: Path,
) -> None:
    seen: set[str] = set()
    for row in results:
        strategy = str(row.get("strategy", ""))
        if strategy not in selected_strategies:
            raise ValueError(
                f"checkpoint contains unrequested strategy result: {strategy!r}"
            )
        if strategy in seen:
            raise ValueError(f"checkpoint contains duplicate strategy result: {strategy}")
        seen.add(strategy)
        ledger = row.get("trade_ledger")
        if not isinstance(ledger, dict):
            raise ValueError(f"checkpoint result for {strategy} has no trade ledger fingerprint")
        path_value, expected_hash = ledger.get("path"), ledger.get("sha256")
        if not isinstance(path_value, str) or not isinstance(expected_hash, str):
            raise ValueError(f"checkpoint result for {strategy} has an invalid trade ledger fingerprint")
        actual = fingerprint_files((project_root / path_value,), project_root)[0]
        if actual["sha256"] != expected_hash:
            raise ValueError(
                f"checkpoint trade ledger changed for {strategy}; use --restart or a new report path"
            )


if __name__ == "__main__":
    raise SystemExit(main())
