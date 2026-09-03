"""Read-only MetaTrader 5 terminal and market-data adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from mt5_scalping_agent.config import Settings


class MT5ConnectionError(RuntimeError):
    """Raised when the terminal cannot be initialized or queried safely."""


class MT5DataError(RuntimeError):
    """Raised when terminal data is missing or invalid."""


@dataclass(frozen=True)
class ConnectionStatus:
    """A non-sensitive view of terminal availability."""

    connected: bool
    terminal_name: str | None = None
    terminal_version: str | None = None


class MT5ReadOnlyClient:
    """Small adapter over the MT5 package with no execution operations."""

    def __init__(self, settings: Settings, mt5_module: Any) -> None:
        self._settings = settings
        self._mt5 = mt5_module
        self._initialized = False

    def connect(self) -> ConnectionStatus:
        """Initialize the terminal session without submitting any request."""
        options: dict[str, Any] = {}
        if self._settings.mt5_path is not None:
            options["path"] = str(self._settings.mt5_path)
        if self._settings.mt5_login is not None:
            options["login"] = self._settings.mt5_login
        if self._settings.mt5_password is not None:
            options["password"] = self._settings.mt5_password
        if self._settings.mt5_server is not None:
            options["server"] = self._settings.mt5_server

        if not self._mt5.initialize(**options):
            raise MT5ConnectionError(f"MT5 initialization failed: {self._last_error()}")

        self._initialized = True
        return self.connection_status()

    def disconnect(self) -> None:
        """Safely release the terminal session."""
        if self._initialized:
            self._mt5.shutdown()
            self._initialized = False

    def connection_status(self) -> ConnectionStatus:
        """Return terminal availability without exposing account credentials."""
        terminal = self._mt5.terminal_info()
        if terminal is None:
            return ConnectionStatus(connected=False)

        return ConnectionStatus(
            connected=True,
            terminal_name=getattr(terminal, "name", None),
            terminal_version=getattr(terminal, "build", None),
        )

    def select_symbol(self, symbol: str) -> None:
        """Make a symbol visible to the terminal before requesting data."""
        self._require_nonempty_symbol(symbol)
        if not self._mt5.symbol_select(symbol, True):
            raise MT5DataError(f"Unable to select {symbol}: {self._last_error()}")
    def account_information(self) -> dict[str, Any]:
        """Read the current account snapshot as plain data."""
        return self._named_value(self._mt5.account_info(), "account information")

    def symbol_information(self, symbol: str) -> dict[str, Any]:
        """Read a symbol's contract and trading metadata."""
        self._require_nonempty_symbol(symbol)
        return self._named_value(self._mt5.symbol_info(symbol), f"symbol information for {symbol}")

    def tick(self, symbol: str) -> dict[str, Any]:
        """Read the latest bid/ask tick for a symbol."""
        self._require_nonempty_symbol(symbol)
        return self._named_value(self._mt5.symbol_info_tick(symbol), f"tick for {symbol}")

    def historical_ohlcv(self, symbol: str, timeframe: int, bars: int) -> pd.DataFrame:
        """Read completed OHLCV bars and normalize timestamps to UTC."""
        self._require_nonempty_symbol(symbol)
        if bars <= 0:
            raise ValueError("bars must be greater than zero")

        rates = self._mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            raise MT5DataError(f"No historical rates returned for {symbol}: {self._last_error()}")

        frame = pd.DataFrame(rates)
        required_columns = {"time", "open", "high", "low", "close", "tick_volume"}
        missing = required_columns.difference(frame.columns)
        if missing:
            raise MT5DataError(f"Historical rates missing required fields: {sorted(missing)}")

        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        return frame.sort_values("time").reset_index(drop=True)

    def _last_error(self) -> str:
        error = self._mt5.last_error()
        return str(error)

    @staticmethod
    def _named_value(value: Any, description: str) -> dict[str, Any]:
        if value is None:
            raise MT5DataError(f"Unable to retrieve {description}")
        if hasattr(value, "_asdict"):
            return dict(value._asdict())
        if isinstance(value, dict):
            return dict(value)
        raise MT5DataError(f"Unexpected {description} response type: {type(value).__name__}")

    @staticmethod
    def _require_nonempty_symbol(symbol: str) -> None:
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
