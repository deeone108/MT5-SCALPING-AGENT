"""Audit frozen cross-pair research costs against read-only MT5 symbol contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

import MetaTrader5 as mt5

from mt5_scalping_agent.config import load_settings
from mt5_scalping_agent.data import MT5ReadOnlyClient
from mt5_scalping_agent.research.cross_pair import (
    CrossPairDevelopmentSpec,
    load_frozen_cost_model,
)
from mt5_scalping_agent.research.manifest import write_json_atomic
from mt5_scalping_agent.risk import SymbolRiskSpec


PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only audit of frozen cross-pair transaction-cost models."
    )
    parser.add_argument("--cost-models", type=Path, default=Path("config/cross_pair_cost_models.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    client = MT5ReadOnlyClient(load_settings(), mt5)
    client.connect()
    try:
        account = client.account_information()
        models: dict[str, object] = {}
        for pair in PAIRS:
            info = client.symbol_information(pair)
            symbol = SymbolRiskSpec(
                symbol=pair,
                point=float(info["point"]),
                tick_size=float(info["trade_tick_size"]),
                tick_value=float(info["trade_tick_value"]),
                volume_min=float(info["volume_min"]),
                volume_max=float(info["volume_max"]),
                volume_step=float(info["volume_step"]),
            )
            spec = CrossPairDevelopmentSpec(pair, symbol)
            models[pair] = {
                "symbol_contract": symbol.model_dump(mode="json"),
                "pip_size": spec.pip_size,
                "base": _model_document(load_frozen_cost_model(args.cost_models, spec, "base"), spec),
                "stress": _model_document(load_frozen_cost_model(args.cost_models, spec, "stress"), spec),
            }
        write_json_atomic(args.report, {
            "purpose": "read-only audit of frozen research transaction costs; not a backtest or execution configuration",
            "account": {key: account.get(key) for key in ("server", "company", "currency", "trade_allowed", "trade_expert")},
            "cost_model_source": args.cost_models.as_posix(),
            "models": models,
        })
    finally:
        client.disconnect()
    print(f"Report: {args.report}")
    return 0


def _model_document(model: object, spec: CrossPairDevelopmentSpec) -> dict[str, object]:
    cost = model
    return {
        "spread_points": cost.spread_points,
        "slippage_points": cost.slippage_points,
        "commission_per_lot_per_side_usd": cost.commission_per_lot_per_side_usd,
        "commission_evidence": cost.commission_evidence,
        "calibration_report": cost.calibration_report.as_posix(),
        "round_trip_cost_pips": cost.round_trip_cost_pips(spec),
    }


if __name__ == "__main__":
    raise SystemExit(main())
