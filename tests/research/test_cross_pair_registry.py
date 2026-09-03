from pathlib import Path

from mt5_scalping_agent.research.cross_pair_registry import load_cross_pair_registry


def test_cross_pair_registry_records_strategy18_early_stop_rejection() -> None:
    registry = load_cross_pair_registry(Path("config/cross_pair_research_registry.json"))

    assert registry.schema_version == 1
    assert len(registry.proposals) == 1
    proposal = registry.proposals[0]
    assert proposal.strategy_name == "london_asian_range_failed_auction"
    assert proposal.status == "REJECTED"
    assert proposal.implementation == "src/mt5_scalping_agent/backtesting/london_asian_range_failed_auction.py"
    assert proposal.experiments_performed[0].decision == "REJECTED_PRIMARY_GATES"
    assert proposal.experiments_performed[0].report_path == "reports/strategy18/strategy18_early_stop_rejection.json"
    assert {binding.symbol for binding in proposal.pair_bindings} == {
        "EURUSD", "GBPUSD", "USDJPY", "USDCAD"
    }