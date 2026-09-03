import pytest

from mt5_scalping_agent.config import (
    ConfigurationError,
    ExecutionNotAllowedError,
    RuntimeMode,
    load_settings,
)


def test_defaults_to_backtest_mode() -> None:
    settings = load_settings({})

    assert settings.mode is RuntimeMode.BACKTEST
    assert settings.database_path.as_posix() == "data/trading.db"


@pytest.mark.parametrize("mode", [RuntimeMode.BACKTEST, RuntimeMode.DEMO, RuntimeMode.LIVE])
def test_accepts_known_runtime_modes(mode: RuntimeMode) -> None:
    settings = load_settings({"MODE": mode})

    assert settings.mode is mode


def test_rejects_unknown_runtime_mode() -> None:
    with pytest.raises(ConfigurationError, match="mode"):
        load_settings({"MODE": "PAPER"})


def test_normalizes_log_level() -> None:
    settings = load_settings({"LOG_LEVEL": "warning"})

    assert settings.log_level == "WARNING"


def test_rejects_unknown_log_level() -> None:
    with pytest.raises(ConfigurationError, match="LOG_LEVEL"):
        load_settings({"LOG_LEVEL": "VERBOSE"})


@pytest.mark.parametrize("mode", list(RuntimeMode))
def test_order_submission_is_disabled_in_every_mode(mode: RuntimeMode) -> None:
    settings = load_settings({"MODE": mode})

    with pytest.raises(ExecutionNotAllowedError, match="disabled"):
        settings.assert_order_submission_allowed()