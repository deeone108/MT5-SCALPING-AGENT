from datetime import UTC, datetime

import pytest

from mt5_scalping_agent.data.historical_tick_source import HistoricalTickSource
from mt5_scalping_agent.data.truefx_tick_source import TrueFxManualDownloadRequired, TrueFxTickSource


START = datetime(2019, 1, 7, tzinfo=UTC)
END = datetime(2019, 1, 14, tzinfo=UTC)


def test_truefx_implements_contract_and_reports_unknowns() -> None:
    source = TrueFxTickSource()
    assert isinstance(source, HistoricalTickSource)
    assert source.source_schema().bid_ask is True
    assert source.source_schema().verified is False
    assert source.source_timestamp_semantics().timezone == "UNVERIFIED"
    assert source.licensing_metadata().authentication_required is True
    assert source.licensing_metadata().automated_download_permitted is None


def test_truefx_acquisition_fails_closed_without_human_download() -> None:
    source = TrueFxTickSource()
    assert source.list_available("EURUSD", START, END) == ()
    with pytest.raises(TrueFxManualDownloadRequired, match="authenticated manual download"):
        source.acquire("EURUSD", START, END)


def test_truefx_rejects_out_of_scope_or_post_2023_requests() -> None:
    source = TrueFxTickSource()
    with pytest.raises(ValueError, match="unsupported"):
        source.acquire("XAUUSD", START, END)
    with pytest.raises(ValueError, match="2024"):
        source.acquire("EURUSD", START, datetime(2024, 1, 2, tzinfo=UTC))
