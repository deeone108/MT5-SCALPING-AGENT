"""Market and broker data access interfaces."""

from mt5_scalping_agent.data.dukascopy_client import DukascopyDataError, DukascopyM1Client
from mt5_scalping_agent.data.histdata_client import HistDataError, HistDataM1Client
from mt5_scalping_agent.data.local_archive import (
    PROVIDER_BOUNDARY,
    LocalArchiveError,
    LocalResearchArchive,
    resample_m1_to_m5,
)
from mt5_scalping_agent.data.quality import (
    DUKASCOPY_PROVENANCE,
    HISTDATA_PROVENANCE,
    M1DataQualityReport,
    ProviderProvenance,
    archive_provenance_inventory,
    audit_m1_frame,
)
from mt5_scalping_agent.data.sessions import (
    MarketSession,
    NEW_YORK_SESSION_SUBSECTIONS,
    active_sessions,
    new_york_session_subsection,
    session_bounds_utc,
    session_name,
)
from mt5_scalping_agent.data.tick_analysis import TickAnalysisError, analyze_tick_spreads
from mt5_scalping_agent.data.tick_capture import TickCaptureError, TickSpreadRecorder
from mt5_scalping_agent.data.mt5_client import (
    ConnectionStatus,
    MT5ConnectionError,
    MT5DataError,
    MT5ReadOnlyClient,
)

__all__ = [
    "ConnectionStatus",
    "DukascopyDataError",
    "DukascopyM1Client",
    "HistDataError",
    "HistDataM1Client",
    "LocalArchiveError",
    "LocalResearchArchive",
    "DUKASCOPY_PROVENANCE",
    "HISTDATA_PROVENANCE",
    "M1DataQualityReport",
    "MarketSession",
    "NEW_YORK_SESSION_SUBSECTIONS",
    "PROVIDER_BOUNDARY",
    "ProviderProvenance",
    "active_sessions",
    "new_york_session_subsection",
    "archive_provenance_inventory",
    "audit_m1_frame",
    "MT5ConnectionError",
    "MT5DataError",
    "MT5ReadOnlyClient",
    "resample_m1_to_m5",
    "session_bounds_utc",
    "session_name",
    "TickAnalysisError",
    "TickCaptureError",
    "analyze_tick_spreads",
    "TickSpreadRecorder",
]
