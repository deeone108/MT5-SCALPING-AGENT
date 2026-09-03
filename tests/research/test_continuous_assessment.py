import copy
import json
from pathlib import Path

import pytest

from mt5_scalping_agent.research.continuous_assessment import (
    ContinuousAssessmentError,
    build_continuous_assessment,
    load_completed_continuous_report,
)
from scripts.generate_continuous_assessment import main


START = "2019-01-01T00:00:00+00:00"
END = "2024-01-01T00:00:00+00:00"
YEARS = tuple(str(year) for year in range(2019, 2024))
QUARTERS = tuple(
    f"{year}-Q{quarter}" for year in range(2019, 2024) for quarter in range(1, 5)
)
MONTHS = tuple(
    f"{year}-{month:02d}" for year in range(2019, 2024) for month in range(1, 13)
)


def periods() -> dict[str, object]:
    return {
        "development": {"start": START, "end": END, "end_exclusive": True},
        "post_selection_robustness": {
            "start": END,
            "permitted_for_this_run": False,
        },
    }


def partition_rows(
    labels: tuple[str, ...], complete: dict[str, object]
) -> list[dict[str, object]]:
    fields = (
        "trade_count",
        "gross_pnl",
        "total_spread_cost",
        "total_slippage_cost",
        "total_commission",
        "total_transaction_cost",
        "net_pnl",
    )
    return [
        {
            "group": label,
            **{
                field: complete[field] if index == 0 else 0
                for field in fields
            },
        }
        for index, label in enumerate(labels)
    ]

def result_row(
    name: str = "cost_failure",
    *,
    gross: float = 100.0,
    net: float = -20.0,
    trade_count: int = 400,
    rejection_reasons: dict[str, int] | None = None,
) -> dict[str, object]:
    total_cost = gross - net
    spread, slippage = 40.0, 20.0
    commission = total_cost - spread - slippage
    gross_expectancy = gross / trade_count
    net_expectancy = net / trade_count
    rejections = rejection_reasons or {}
    complete = {
        "trade_count": trade_count,
        "total_lots": 10.0,
        "gross_pnl": gross,
        "total_spread_cost": spread,
        "total_slippage_cost": slippage,
        "total_commission": commission,
        "total_transaction_cost": total_cost,
        "net_pnl": net,
        "net_profit": net,
        "gross_expectancy_per_trade": gross_expectancy,
        "net_expectancy_per_trade": net_expectancy,
        "break_even_transaction_cost_per_trade": gross_expectancy if gross >= 0 else None,
        "break_even_spread_points": 2.5 if gross >= 0 else None,
        "rejected_intent_count": sum(rejections.values()),
        "rejected_intent_reason_counts": rejections,
    }
    consistency = {
        "yearly": {
            "period_count": 5,
            "active_period_count": 5,
            "positive_period_count": 2,
            "negative_period_count": 3,
            "positive_period_fraction": 0.4,
            "positive_active_period_fraction": 0.4,
            "strongest_period": {"period": "2020", "net_pnl": 40.0},
            "weakest_period": {"period": "2023", "net_pnl": -50.0},
            "periods": [
                {"period": "2019", "trade_count": 80, "gross_pnl": 30.0, "net_pnl": -5.0},
                {"period": "2020", "trade_count": 80, "gross_pnl": 60.0, "net_pnl": 40.0},
                {"period": "2021", "trade_count": 80, "gross_pnl": 20.0, "net_pnl": -10.0},
                {"period": "2022", "trade_count": 80, "gross_pnl": 30.0, "net_pnl": 5.0},
                {"period": "2023", "trade_count": 80, "gross_pnl": -40.0, "net_pnl": -50.0},
            ],
        },
        "monthly": {
            "period_count": 60,
            "active_period_count": 60,
            "positive_period_count": 20,
            "negative_period_count": 40,
            "positive_period_fraction": 1 / 3,
            "positive_active_period_fraction": 1 / 3,
            "strongest_period": {"period": "2020-04", "net_pnl": 25.0},
            "weakest_period": {"period": "2023-10", "net_pnl": -30.0},
            "periods": [
                {
                    "period": month,
                    "trade_count": trade_count if index == 0 else 0,
                    "gross_pnl": gross if index == 0 else 0.0,
                    "total_transaction_cost": total_cost if index == 0 else 0.0,
                    "net_pnl": net if index == 0 else 0.0,
                }
                for index, month in enumerate(MONTHS)
            ],
        },
    }
    statistics = {
        "methodology": {
            "bootstrap_method": "IID completed-trade resampling with replacement",
            "bootstrap_rng": "NumPy PCG64",
            "serial_dependence_preserved": False,
            "settings": {"random_seed": 20260824, "bootstrap_samples": 1000},
        },
        "sample": {
            "trade_count": trade_count,
            "gross_pnl": gross,
            "total_transaction_cost": total_cost,
            "net_pnl": net,
            "accounting_identity_residual": 0.0,
            "accounting_identity_holds": True,
        },
        "bootstrap": {
            "gross_expectancy_per_trade": {
                "point_estimate": gross_expectancy,
                "lower": gross_expectancy - 0.1,
                "upper": gross_expectancy + 0.1,
                "confidence_level": 0.95,
            },
            "net_expectancy_per_trade": {
                "point_estimate": net_expectancy,
                "lower": net_expectancy - 0.1,
                "upper": net_expectancy + 0.1,
                "confidence_level": 0.95,
            },
            "profit_factor": {"point_estimate": 0.9},
            "maximum_drawdown": {"point_estimate": 200.0},
        },
        "consistency": consistency,
        "concentration": {
            "top_trade_basis": "positive-trade profit pool",
            "strongest_period_basis": "positive aggregate period pool",
            "gross_by_top_trades": [],
            "net_by_top_trades": [
                {
                    "top_trade_fraction": 0.1,
                    "top_trade_count": 40,
                    "contribution_fraction": 0.6,
                    "contribution_percent": 60.0,
                }
            ],
            "strongest_year": {
                "gross": {"period": "2020", "contribution_fraction": 0.4},
                "net": {"period": "2020", "period_pnl": 40.0, "contribution_fraction": 0.7},
            },
            "strongest_month": {
                "gross": {"period": "2020-04", "contribution_fraction": 0.3},
                "net": {"period": "2020-04", "period_pnl": 25.0, "contribution_fraction": 0.5},
            },
        },
        "downside_tail": {
            "pnl_quantile": -12.0,
            "expected_shortfall": -18.0,
            "maximum_consecutive_losses": 6,
        },
    }
    return {
        "strategy": name,
        "period": {
            "name": "development",
            "start": START,
            "end": END,
            "end_exclusive": True,
            "post_selection_data_used": False,
        },
        "attribution_basis": "trade_entry_time",
        "session_definition": (
            "DST-aware Europe/London and America/New_York local 08:00-13:00"
        ),
        "volatility_regime_definition": {
            "kind": "lagged_atr_relative_to_trailing_median",
            "signal_rule": False,
            "observation_timing": "only candles completed before trade entry",
        },
        "summaries": {
            "complete": complete,
            "by_year": partition_rows(YEARS, complete),
            "by_quarter": partition_rows(QUARTERS, complete),
            "by_month": partition_rows(MONTHS, complete),
            "by_direction": partition_rows(("BUY", "SELL"), complete),
            "by_session": partition_rows(
                ("off_session", "london", "new_york", "london_new_york"), complete
            ),
            "by_volatility_regime": partition_rows(
                ("low", "normal", "high", "unavailable"), complete
            ),
        },
        "statistical_robustness": statistics,
        "trade_ledger": {"path": f"details/{name}.json", "sha256": "sha256:test"},
    }


def completed_report() -> dict[str, object]:
    return {
        "purpose": "continuous development diagnostics",
        "symbol": "EURUSD",
        "periods": periods(),
        "backtest_assumptions": {
            "initial_balance": 10_000.0,
            "spread_points": 2.0,
            "slippage_points": 1.0,
            "commission_per_lot_per_side": 2.0,
        },
        "risk_profile": "research_diagnostics",
        "run_manifest": {
            "run_id": "continuous_development_evaluation:test",
            "frozen": {
                "run_kind": "continuous_development_evaluation",
                "timeframe": "M1",
                "periods": periods(),
                "strategies": [{"strategy_name": "cost_failure"}],
                "transaction_costs": {
                    "spread_points": 2.0,
                    "slippage_points": 1.0,
                    "commission_model": {
                        "amount": 2.0,
                        "kind": "fixed_per_lot_per_side",
                    },
                },
                "runner_settings": {"risk_profile": "research_diagnostics"},
            },
        },
        "results": [result_row()],
    }


def test_assessment_is_deterministic_and_covers_all_eight_points() -> None:
    report = completed_report()

    first_machine, first_markdown = build_continuous_assessment(
        report, source_label="report.json"
    )
    second_machine, second_markdown = build_continuous_assessment(
        report, source_label="report.json"
    )

    assert first_machine == second_machine
    assert first_markdown == second_markdown
    points = first_machine["required_diagnosis"]
    assert [value["required_point"] for value in points.values()] == list(range(1, 9))
    strategy = first_machine["strategies"][0]
    assert strategy["costs"]["transaction_cost_per_trade"] == pytest.approx(0.3)
    assert strategy["break_even"]["commission_per_lot_per_side"] == pytest.approx(2.0)
    assert strategy["failure_mechanism"]["dominant"] == "TRANSACTION_COSTS"
    temporal = strategy["temporal_stability"]
    assert temporal["quarterly"]["group_count"] == 20
    assert temporal["directions"]["group_count"] == 2
    assert temporal["sessions"]["group_count"] == 4
    assert temporal["volatility_regimes"]["group_count"] == 4
    assert "DST-aware" in temporal["session_definition"]
    assert first_machine["decision"]["new_strategy_proposed"] is False
    for heading in (
        "1. Gross Edge",
        "2. Exact Cost Decomposition",
        "3. Average Gross Edge Per Trade",
        "4. Transaction Cost Per Trade",
        "5. Break-Even Cost Levels",
        "6. Profit Concentration",
        "7. Temporal Stability",
        "8. Dominant Failure Mechanism",
    ):
        assert heading in first_markdown
    assert "M1 OHLC" in first_markdown
    assert "IID" in first_markdown
    assert "does not propose a new strategy" in first_markdown
    json.dumps(first_machine, allow_nan=False)


def test_failure_classification_prioritizes_signal_quality_and_risk_censorship() -> None:
    signal_report = completed_report()
    signal_report["results"] = [result_row(gross=-10.0, net=-130.0)]
    signal_machine, _ = build_continuous_assessment(signal_report)
    assert signal_machine["strategies"][0]["failure_mechanism"]["dominant"] == "SIGNAL_QUALITY"

    censored_report = completed_report()
    censored_report["results"] = [
        result_row(
            rejection_reasons={"maximum mark-to-market drawdown has been reached": 10}
        )
    ]
    censored_machine, _ = build_continuous_assessment(censored_report)
    assert censored_machine["strategies"][0]["failure_mechanism"]["dominant"] == "RISK_CENSORSHIP"

    depleted_report = completed_report()
    depleted_report["results"] = [
        result_row(
            rejection_reasons={
                "calculated position size is below the broker minimum volume": 500
            }
        )
    ]
    depleted_machine, _ = build_continuous_assessment(depleted_report)
    depleted_failure = depleted_machine["strategies"][0]["failure_mechanism"]
    assert depleted_failure["dominant"] == "TRANSACTION_COSTS"
    assert "CAPITAL_DEPLETION_OR_MINIMUM_VOLUME" in depleted_failure["contributors"]
    assert depleted_failure["evidence"]["minimum_volume_rejection_count"] == 500


def test_rejects_checkpoint_incomplete_split_leakage_and_bad_accounting(tmp_path: Path) -> None:
    with pytest.raises(ContinuousAssessmentError, match="checkpoint"):
        build_continuous_assessment({"checkpoint_schema_version": 2})

    checkpoint_path = tmp_path / "run.checkpoint.json"
    checkpoint_path.write_text(json.dumps(completed_report()), encoding="utf-8")
    with pytest.raises(ContinuousAssessmentError, match="checkpoint"):
        load_completed_continuous_report(checkpoint_path)

    incomplete = completed_report()
    incomplete["run_manifest"]["frozen"]["strategies"].append(
        {"strategy_name": "missing_result"}
    )
    with pytest.raises(ContinuousAssessmentError, match="result set"):
        build_continuous_assessment(incomplete)

    leaked = completed_report()
    leaked["periods"]["development"]["end"] = "2025-01-01T00:00:00+00:00"
    with pytest.raises(ContinuousAssessmentError, match="isolated"):
        build_continuous_assessment(leaked)

    broken = completed_report()
    broken["results"][0]["summaries"]["complete"]["net_pnl"] = -21.0
    with pytest.raises(ContinuousAssessmentError, match="identity"):
        build_continuous_assessment(broken)
    mismatched_profile = completed_report()
    mismatched_profile["risk_profile"] = "deployment_limits"
    with pytest.raises(ContinuousAssessmentError, match="risk profile"):
        build_continuous_assessment(mismatched_profile)

    partition_mismatch = completed_report()
    partition_mismatch["results"][0]["summaries"]["by_direction"][0]["gross_pnl"] += 1
    with pytest.raises(ContinuousAssessmentError, match="does not reconcile"):
        build_continuous_assessment(partition_mismatch)

    statistical_leak = completed_report()
    statistical_leak["results"][0]["statistical_robustness"]["consistency"][
        "monthly"
    ]["periods"][-1]["period"] = "2024-01"
    with pytest.raises(ContinuousAssessmentError, match="leak outside"):
        build_continuous_assessment(statistical_leak)

    noncausal = completed_report()
    noncausal["results"][0]["volatility_regime_definition"]["signal_rule"] = True
    with pytest.raises(ContinuousAssessmentError, match="not causal"):
        build_continuous_assessment(noncausal)


def test_cli_writes_both_artifacts_without_overwriting_source(tmp_path: Path) -> None:
    source = tmp_path / "completed.json"
    source.write_text(json.dumps(completed_report()), encoding="utf-8")

    assert main([str(source)]) == 0

    json_path = tmp_path / "completed_assessment.json"
    markdown_path = tmp_path / "completed_assessment.md"
    assert json_path.is_file()
    assert markdown_path.is_file()
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert "# Continuous Development Diagnosis" in markdown_path.read_text(encoding="utf-8")
    assert main([str(source), "--json-output", str(source)]) == 1
