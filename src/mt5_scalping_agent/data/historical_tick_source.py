"""Provider-neutral contracts for read-only historical tick acquisition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class TickSourceSchema:
    fields: tuple[str, ...]
    bid_ask: bool
    volume_semantics: str
    verified: bool


@dataclass(frozen=True)
class TickTimestampSemantics:
    precision: str
    timezone: str
    verified: bool


@dataclass(frozen=True)
class TickSourceLicense:
    use: str
    authentication_required: bool
    automated_download_permitted: bool | None
    terms_url: str


@dataclass(frozen=True)
class TickSourceArtifact:
    path: Path
    provider: str


class HistoricalTickSource(ABC):
    """Separate provider access from normalized archive construction."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def list_available(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]: ...

    @abstractmethod
    def acquire(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]: ...

    @abstractmethod
    def source_timestamp_semantics(self) -> TickTimestampSemantics: ...

    @abstractmethod
    def source_schema(self) -> TickSourceSchema: ...

    @abstractmethod
    def licensing_metadata(self) -> TickSourceLicense: ...
