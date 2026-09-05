"""Fail-closed TrueFX historical-tick source boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mt5_scalping_agent.data.historical_tick_source import (
    HistoricalTickSource,
    TickSourceArtifact,
    TickSourceLicense,
    TickSourceSchema,
    TickTimestampSemantics,
)


class TrueFxManualDownloadRequired(RuntimeError):
    """Raised when authenticated provider action is required."""


class TrueFxTickSource(HistoricalTickSource):
    """Offline boundary for manually supplied, provider-native TrueFX files."""

    TERMS_URL = "https://www.truefx.com/truefx-terms-and-conditions/"
    DOWNLOADS_URL = "https://www.truefx.com/truefx-historical-downloads-2/"
    SUPPORTED_PAIRS = frozenset({"EURUSD", "GBPUSD", "USDJPY", "USDCAD"})

    def __init__(self, inbox: Path = Path("data/ticks/inbox/truefx")) -> None:
        self._inbox = inbox

    @property
    def provider_name(self) -> str:
        return "truefx"

    def list_available(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]:
        self._validate_request(pair, start, end)
        return ()

    def acquire(self, pair: str, start: datetime, end: datetime) -> tuple[TickSourceArtifact, ...]:
        self._validate_request(pair, start, end)
        raise TrueFxManualDownloadRequired(
            "TrueFX historical data requires authenticated manual download; "
            f"place untouched provider-native files under {self._inbox} for reviewed offline import"
        )

    def source_timestamp_semantics(self) -> TickTimestampSemantics:
        return TickTimestampSemantics(precision="millisecond detail", timezone="UNVERIFIED", verified=False)

    def source_schema(self) -> TickSourceSchema:
        return TickSourceSchema(
            fields=("timestamp", "bid", "ask"),
            bid_ask=True,
            volume_semantics="UNVERIFIED / missing volume must normalize to null",
            verified=False,
        )

    def licensing_metadata(self) -> TickSourceLicense:
        return TickSourceLicense(
            use="single-instance internal viewing and analysis; no redistribution",
            authentication_required=True,
            automated_download_permitted=None,
            terms_url=self.TERMS_URL,
        )

    @classmethod
    def _validate_request(cls, pair: str, start: datetime, end: datetime) -> None:
        if pair.upper() not in cls.SUPPORTED_PAIRS:
            raise ValueError(f"unsupported Phase 22 pair: {pair}")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start.astimezone(UTC) >= end.astimezone(UTC):
            raise ValueError("start must be earlier than end")
        if end.astimezone(UTC) > datetime(2024, 1, 1, tzinfo=UTC):
            raise ValueError("Phase 22 source requests must not access 2024 or later")
