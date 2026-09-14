"""Faithful, non-executing adapters for the pinned XAU-60 v2.1 strategies."""

from .adapters import (
    CRTTBSAdapter,
    SMCScalperAdapter,
    TrendBreakTraumaAdapter,
    XAU60_PIN,
    XAU60_SOURCE_ROOT_SHA256,
)

__all__ = [
    "CRTTBSAdapter",
    "SMCScalperAdapter",
    "TrendBreakTraumaAdapter",
    "XAU60_PIN",
    "XAU60_SOURCE_ROOT_SHA256",
]
