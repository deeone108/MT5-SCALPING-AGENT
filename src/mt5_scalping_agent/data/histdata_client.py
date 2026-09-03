"""Read-only annual M1 importer for HistData Generic ASCII archives."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC
from typing import Any

import pandas as pd
import requests

from mt5_scalping_agent.data.validation import MarketDataValidationError, validate_ohlcv


class HistDataError(RuntimeError):
    """Raised when a HistData archive cannot be retrieved or normalized safely."""


class HistDataM1Client:
    """Download public bid-side annual M1 archives and normalize fixed EST to UTC."""

    _base_url = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"

    def __init__(self, session: requests.Session | Any | None = None) -> None:
        self._session = session or requests.Session()

    def annual_ohlcv(self, symbol: str, year: int) -> pd.DataFrame:
        """Return validated annual M1 bid OHLCV data for a supported FX symbol."""
        normalized_symbol = symbol.upper()
        if not re.fullmatch(r"[A-Z]{6}", normalized_symbol):
            raise ValueError("symbol must be a six-letter FX pair")
        if not 2000 <= year <= 2100:
            raise ValueError("year must be between 2000 and 2100")

        page_url = f"{self._base_url}/{normalized_symbol.lower()}/{year}"
        page = self._session.get(page_url, timeout=30)
        _raise_for_status(page, "HistData download page")
        token_match = re.search(r'id=["\']tk["\'][^>]*value=["\']([^"\']+)', page.text)
        if token_match is None:
            raise HistDataError("HistData download token was not found")
        response = self._session.post(
            "https://www.histdata.com/get.php",
            data={
                "tk": token_match.group(1),
                "date": str(year),
                "datemonth": str(year),
                "platform": "ASCII",
                "timeframe": "M1",
                "fxpair": normalized_symbol,
            },
            headers={"Referer": page_url},
            timeout=120,
        )
        _raise_for_status(response, "HistData archive")
        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            members = [member for member in archive.namelist() if member.lower().endswith(".csv")]
            if len(members) != 1:
                raise HistDataError("HistData archive must contain exactly one CSV file")
            raw = pd.read_csv(
                archive.open(members[0]),
                sep=";",
                header=None,
                names=["time", "open", "high", "low", "close", "tick_volume"],
            )
        except (zipfile.BadZipFile, UnicodeDecodeError, pd.errors.ParserError) as error:
            raise HistDataError("HistData archive could not be parsed") from error
        if raw.empty:
            raise HistDataError(f"HistData archive is empty for {normalized_symbol} {year}")

        local_time = pd.to_datetime(raw["time"], format="%Y%m%d %H%M%S", errors="raise")
        raw["time"] = local_time.dt.tz_localize("Etc/GMT+5").dt.tz_convert(UTC)
        try:
            return validate_ohlcv(raw)
        except MarketDataValidationError as error:
            raise HistDataError(f"HistData archive failed OHLCV validation: {error}") from error


def _raise_for_status(response: Any, description: str) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise HistDataError(f"{description} request failed") from error
