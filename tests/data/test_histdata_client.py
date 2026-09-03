import io
import zipfile

import pytest

from mt5_scalping_agent.data.histdata_client import HistDataError, HistDataM1Client


class Response:
    def __init__(self, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class Session:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.post_data = None

    def get(self, url, timeout):  # type: ignore[no-untyped-def]
        return Response('<input id="tk" value="test-token">')

    def post(self, url, data, headers, timeout):  # type: ignore[no-untyped-def]
        self.post_data = data
        return Response(content=self.archive)


def make_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("DAT_ASCII_EURUSD_M1_2006.csv", "20060102 000000;1.1;1.2;1.0;1.15;0\n")
    return buffer.getvalue()


def test_downloads_and_normalizes_fixed_est_bars_to_utc() -> None:
    session = Session(make_archive())
    result = HistDataM1Client(session).annual_ohlcv("EURUSD", 2006)

    assert session.post_data["fxpair"] == "EURUSD"
    assert result["time"].iloc[0].isoformat() == "2006-01-02T05:00:00+00:00"
    assert result["close"].iloc[0] == 1.15


def test_rejects_invalid_symbol_and_archive() -> None:
    with pytest.raises(ValueError, match="six-letter"):
        HistDataM1Client(Session(make_archive())).annual_ohlcv("EUR/USD", 2006)
    with pytest.raises(HistDataError, match="parsed"):
        HistDataM1Client(Session(b"not-a-zip")).annual_ohlcv("EURUSD", 2006)
