"""
浏览器自动化模块：Playwright 驱动抖音 PC 网页版。
M2 产出：engine、selectors、risk；Cookie 持久化与风控。
"""
from __future__ import annotations

from .engine import BrowserEngine
from .risk import RiskConfig, RiskLevel, RiskState
from . import selectors

__all__ = [
    "BrowserEngine",
    "RiskConfig",
    "RiskLevel",
    "RiskState",
    "selectors",
]
