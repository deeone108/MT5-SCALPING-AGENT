"""Project boundary around the immutable XAU-60 strategy snapshot.

The adapters validate completed-bar causality and translate the upstream
``TradeSignal`` into this project's non-executing ``SignalProposal``. They do
not alter upstream entry, exit, stop, target, scoring, or state transitions.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib import import_module
from math import isfinite
from pathlib import Path
import sys
from typing import Any, ClassVar

import pandas as pd

from mt5_scalping_agent.domain import SignalProposal, TradeDirection

XAU60_PIN = "b877fdb1fcc5888b1443cf0214ea89f8040e8096"
XAU60_SOURCE_ROOT_SHA256 = "ea6f51dc468e2baec323ba5b37ee7e37543a897cef99db546f8a63ef10858dd7"
_SOURCE = Path(__file__).resolve().parents[4] / "third_party" / "xau60" / XAU60_PIN / "source"
_BASE_COLUMNS = frozenset({"time", "open", "high", "low", "close"})


class XAU60InputError(ValueError):
    """Raised when the project boundary cannot prove a causal upstream input."""


def _load_upstream(module: str, class_name: str) -> Any:
    """Load the pinned implementation without copying or mutating its source."""
    source = str(_SOURCE)
    if source not in sys.path:
        sys.path.insert(0, source)
    try:
        return getattr(import_module(module), class_name)
    except ModuleNotFoundError as exc:
        if exc.name == "ta":
            raise RuntimeError("XAU-60 adapters require the upstream 'ta' dependency") from exc
        raise


class _Adapter:
    module: ClassVar[str]
    class_name: ClassVar[str]
    name: ClassVar[str]
    timeframe: ClassVar[str]
    interval: ClassVar[timedelta]
    minimum_bars: ClassVar[int]
    required_columns: ClassVar[frozenset[str]] = _BASE_COLUMNS | {"volume"}
    default_config: ClassVar[dict[str, Any]]

    def __init__(self, upstream: Any | None = None) -> None:
        self._upstream = upstream if upstream is not None else _load_upstream(self.module, self.class_name)()
        self._upstream.initialize(deepcopy(self.default_config))

    @classmethod
    def provenance(cls) -> dict[str, str]:
        return {
            "upstream_commit": XAU60_PIN,
            "source_root_sha256": XAU60_SOURCE_ROOT_SHA256,
            "upstream_module": cls.module,
            "upstream_class": cls.class_name,
        }

    def propose(self, symbol: str, bars: pd.DataFrame, observed_at: datetime) -> SignalProposal:
        frame, now = self._validated_frame(symbol, bars, observed_at)
        if len(frame) < self.minimum_bars:
            return self._no_trade(symbol, now, "insufficient completed bars")
        signal = self._upstream.analyze(symbol, frame)
        if signal is None:
            return self._no_trade(symbol, now, "upstream strategy emitted no signal")
        validated = self._validated_signal(symbol, signal)
        if validated is None:
            return self._no_trade(symbol, now, "upstream strategy emitted HOLD")
        direction, entry_price, stop_loss, take_profit, comment = validated
        return SignalProposal(
            symbol=symbol,
            direction=direction,
            strategy=self.name,
            generated_at=now,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasons=(comment,),
        )

    def _validated_signal(
        self, requested_symbol: str, signal: Any
    ) -> tuple[TradeDirection, float, float, float, str] | None:
        emitted_symbol = getattr(signal, "symbol", None)
        if emitted_symbol != requested_symbol:
            raise XAU60InputError(
                f"upstream symbol mismatch: expected {requested_symbol}, got {emitted_symbol!r}"
            )

        raw_direction = getattr(signal, "signal", None)
        direction_name = getattr(raw_direction, "name", None)
        if direction_name not in {"BUY", "SELL", "HOLD"}:
            raise XAU60InputError(f"unsupported upstream direction: {direction_name!r}")
        if direction_name == "HOLD":
            return None

        prices: dict[str, float] = {}
        for field in ("entry_price", "stop_loss", "take_profit"):
            raw_value = getattr(signal, field, None)
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise XAU60InputError(f"invalid upstream {field}") from exc
            if not isfinite(value) or value <= 0:
                raise XAU60InputError(f"invalid upstream {field}")
            prices[field] = value

        if direction_name == "BUY" and not (
            prices["stop_loss"] < prices["entry_price"] < prices["take_profit"]
        ):
            raise XAU60InputError("invalid upstream BUY price geometry")
        if direction_name == "SELL" and not (
            prices["take_profit"] < prices["entry_price"] < prices["stop_loss"]
        ):
            raise XAU60InputError("invalid upstream SELL price geometry")

        return (
            TradeDirection[direction_name],
            prices["entry_price"],
            prices["stop_loss"],
            prices["take_profit"],
            str(getattr(signal, "comment", "")),
        )

    def _validated_frame(
        self, symbol: str, bars: pd.DataFrame, observed_at: datetime
    ) -> tuple[pd.DataFrame, datetime]:
        if symbol != "XAUUSD":
            raise XAU60InputError("pinned XAU-60 adapters accept exactly XAUUSD")
        if observed_at.tzinfo is None:
            raise XAU60InputError("observed_at must be timezone-aware")
        missing = self.required_columns.difference(bars.columns)
        if missing:
            raise XAU60InputError(f"missing required columns: {sorted(missing)}")
        frame = bars.copy()
        times = pd.to_datetime(frame["time"], utc=True, errors="raise")
        if times.isna().any() or not times.is_monotonic_increasing or times.duplicated().any():
            raise XAU60InputError("bar timestamps must be unique and increasing")
        if len(times) > 1 and not (times.diff().iloc[1:] == self.interval).all():
            raise XAU60InputError(f"bars must have exact {self.timeframe} cadence")
        now = observed_at.astimezone(UTC)
        if len(times) and times.iloc[-1].to_pydatetime() + self.interval > now:
            raise XAU60InputError("latest bar is not completed at observed_at")
        numeric = [column for column in self.required_columns if column != "time"]
        values = frame[numeric].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any() or not values.map(isfinite).to_numpy().all():
            raise XAU60InputError("bar values must be finite numbers")
        if ((values[["open", "high", "low", "close"]] <= 0).any().any()
                or (values["high"] < values[["open", "close", "low"]].max(axis=1)).any()
                or (values["low"] > values[["open", "close", "high"]].min(axis=1)).any()
                or (values["volume"] < 0).any()):
            raise XAU60InputError("invalid OHLCV invariants")
        frame["time"] = times
        frame[numeric] = values
        return frame.reset_index(drop=True), now

    def _no_trade(self, symbol: str, now: datetime, reason: str) -> SignalProposal:
        return SignalProposal(
            symbol=symbol,
            direction=TradeDirection.NO_TRADE,
            strategy=self.name,
            generated_at=now,
            reasons=(reason,),
        )


class SMCScalperAdapter(_Adapter):
    module = "strategies.smc_scalper"
    class_name = "SMCScalper"
    name = "xau60_smc_scalper_v2_1"
    timeframe = "M15"
    interval = timedelta(minutes=15)
    minimum_bars = 50
    required_columns = _BASE_COLUMNS | {"volume", "spread"}
    default_config = {
        "name": "SMC Scalper", "enabled": True, "symbols": ["XAUUSD"],
        "timeframe": "M15", "magic_number": 789123,
        "parameters": {"choch_lookback": 50, "fvg_min_pips": 5.0, "ob_lookback": 20,
                       "risk_reward": 2.0, "trailing_stop": True, "trailing_pips": 50.0,
                       "use_atr_sl": True, "atr_period": 14, "atr_multiplier": 2.0,
                       "stop_loss_pips": 100.0},
        "risk": {"max_risk_percent": 2.0, "lot_size": 0.01},
        "session": {"start_hour": 8, "end_hour": 18, "trade_friday": False},
    }


class TrendBreakTraumaAdapter(_Adapter):
    module = "strategies.trend_break_trauma"
    class_name = "TrendBreakTrauma"
    name = "xau60_trend_break_trauma_v2_1"
    timeframe = "H1"
    interval = timedelta(hours=1)
    minimum_bars = 50
    default_config = {
        "name": "Trend Break Trauma", "enabled": True, "symbols": ["XAUUSD"],
        "timeframe": "H1", "magic_number": 789456,
        "parameters": {"rsi_period": 14, "rsi_overbought": 70.0, "rsi_oversold": 30.0,
                       "trauma_period": 21, "trendline_lookback": 50,
                       "trendline_min_touches": 3, "breakout_confirm_bars": 2},
        "risk": {"stop_loss_pips": 100.0, "take_profit_pips": 200.0,
                 "trailing_stop": False, "trailing_pips": 50.0,
                 "max_risk_percent": 2.0, "lot_size": 0.01},
        "session": {"use_time_filter": True, "start_hour": 0, "end_hour": 23,
                    "trade_friday": True},
    }


class CRTTBSAdapter(_Adapter):
    module = "strategies.crt_tbs"
    class_name = "CRTStrategy"
    name = "xau60_crt_tbs_v2_1"
    timeframe = "M5"
    interval = timedelta(minutes=5)
    minimum_bars = 20
    default_config = {
        "name": "CRT TBS", "enabled": True, "symbols": ["XAUUSD"],
        "timeframe": "M5", "range_timeframe": "H1", "magic_number": 789789,
        "parameters": {"fixed_rr": 2.0, "max_trades_per_killzone": 1,
                       "sl_pips_beyond_sweep": 10.0, "use_range_tp": True},
        "risk": {"lot_size": 0.1, "max_risk_percent": 2.0},
        "session": {"asian": {"start_hour": 0, "end_hour": 6},
                    "london_killzone": {"start_hour": 7, "end_hour": 9},
                    "ny_killzone": {"start_hour": 13, "end_hour": 15}},
    }
