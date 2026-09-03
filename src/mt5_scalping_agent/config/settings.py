"""Typed runtime settings and trading-mode safety boundaries."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuntimeMode(StrEnum):
    """Supported runtime modes, ordered from research to production."""

    BACKTEST = "BACKTEST"
    DEMO = "DEMO"
    LIVE = "LIVE"


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid or unsafe."""


class ExecutionNotAllowedError(RuntimeError):
    """Raised when code attempts broker order submission before approval."""


class Settings(BaseModel):
    """Validated application configuration loaded from an explicit environment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RuntimeMode = RuntimeMode.BACKTEST
    log_level: str = "INFO"
    database_path: Path = Path("data/trading.db")
    mt5_login: int | None = None
    mt5_password: str | None = Field(default=None, repr=False)
    mt5_server: str | None = None
    mt5_path: Path | None = None
    live_trading_confirmation: str | None = Field(default=None, repr=False)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")
        return normalized

    def assert_order_submission_allowed(self) -> None:
        """Block execution until a separately reviewed execution phase exists."""
        raise ExecutionNotAllowedError(
            "Broker order submission is disabled. This foundation supports "
            "research and backtesting only."
        )


def load_settings(
    environment: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """Load settings from a supplied mapping or local environment variables."""
    if environment is None:
        load_dotenv(dotenv_path=dotenv_path)
        environment = os.environ

    values = {
        "mode": environment.get("MODE", RuntimeMode.BACKTEST),
        "log_level": environment.get("LOG_LEVEL", "INFO"),
        "database_path": environment.get("DATABASE_PATH", "data/trading.db"),
        "mt5_login": environment.get("MT5_LOGIN") or None,
        "mt5_password": environment.get("MT5_PASSWORD") or None,
        "mt5_server": environment.get("MT5_SERVER") or None,
        "mt5_path": environment.get("MT5_PATH") or None,
        "live_trading_confirmation": environment.get("LIVE_TRADING_CONFIRMATION") or None,
    }
    try:
        return Settings(**values)
    except ValueError as error:
        raise ConfigurationError(f"Invalid runtime configuration: {error}") from error