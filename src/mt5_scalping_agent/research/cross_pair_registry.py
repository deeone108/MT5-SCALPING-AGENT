"""Strict preregistration records for candidates evaluated across multiple pairs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from mt5_scalping_agent.research.registry import FrozenStrategySpecification, StrictModel


class CrossPairRegistryError(ValueError):
    """Raised when a cross-pair proposal is incomplete or inconsistent."""


class PairBinding(StrictModel):
    symbol: str = Field(min_length=1)
    development_archive_pattern: str = Field(min_length=1)
    base_cost_scenario: str = Field(min_length=1)
    stress_cost_scenario: str = Field(min_length=1)


class CrossPairExperiment(StrictModel):
    experiment_id: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    recorded_at: datetime
    decision: str = Field(min_length=1)


class CrossPairProposal(StrictModel):
    research_id: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    proposed_at: datetime
    hypothesis: str = Field(min_length=1)
    economic_rationale: str = Field(min_length=1)
    frozen_rules: tuple[str, ...] = Field(min_length=1)
    frozen_parameters: dict[str, object]
    frozen_specification: FrozenStrategySpecification
    pair_bindings: tuple[PairBinding, ...] = Field(min_length=2)
    status: str
    implementation: str | None = None
    experiments_performed: tuple[CrossPairExperiment, ...] = ()

    @field_validator("frozen_parameters")
    @classmethod
    def finite_json(cls, value: dict[str, object]) -> dict[str, object]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("frozen_parameters must be finite JSON") from error
        return value

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> "CrossPairProposal":
        if self.status == "PROPOSED":
            if self.implementation is not None or self.experiments_performed:
                raise ValueError("new cross-pair proposals must be unimplemented and unevaluated")
        elif self.status == "REJECTED":
            if not self.implementation or not self.experiments_performed:
                raise ValueError("rejected cross-pair proposals require implementation and evidence")
        else:
            raise ValueError("cross-pair proposal status must be PROPOSED or REJECTED")
        symbols = [item.symbol for item in self.pair_bindings]
        if len(symbols) != len(set(symbols)):
            raise ValueError("pair bindings must be unique")
        return self

class CrossPairResearchRegistry(StrictModel):
    schema_version: int = 1
    registry_id: str = Field(min_length=1)
    updated_at: datetime
    proposals: tuple[CrossPairProposal, ...] = ()

    @model_validator(mode="after")
    def unique_proposals(self) -> "CrossPairResearchRegistry":
        ids = [item.research_id for item in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("cross-pair research IDs must be unique")
        return self


def load_cross_pair_registry(path: Path) -> CrossPairResearchRegistry:
    try:
        return CrossPairResearchRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CrossPairRegistryError(f"could not load cross-pair registry: {path}") from error
