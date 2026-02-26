"""
分级风控：正常 / 预警 / 危险 三级响应，参数可配置。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """风控级别。"""
    NORMAL = "normal"
    WARNING = "warning"
    DANGER = "danger"


@dataclass
class RiskConfig:
    """风控参数配置。"""
    # 正常操作间隔（秒），翻页等
    normal_delay_range: tuple[float, float] = (1.0, 3.0)
    # 页面切换间隔（秒）
    page_delay_range: tuple[float, float] = (2.0, 5.0)
    # 预警后暂停时间（秒），5~15 分钟
    warning_pause_range: tuple[int, int] = (300, 900)
    # 触发危险所需的预警次数
    warning_threshold: int = 3
    # 预警计数窗口（秒），30 分钟
    warning_window: int = 1800
    # 单次操作最大重试次数
    max_retry: int = 2


class RiskState:
    """
    风控状态：记录预警时间戳，在时间窗口内达到阈值则升级为危险。
    线程/协程内使用，由 BrowserEngine 持有。
    """

    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._warning_timestamps: list[float] = []
        self._level: RiskLevel = RiskLevel.NORMAL
        self._on_warning: Optional[Callable[[], None]] = None
        self._on_danger: Optional[Callable[[], None]] = None

    def set_callbacks(
        self,
        on_warning: Optional[Callable[[], None]] = None,
        on_danger: Optional[Callable[[], None]] = None,
    ) -> None:
        """设置预警/危险时的回调（如通知前端）。"""
        self._on_warning = on_warning
        self._on_danger = on_danger

    def _prune_old_warnings(self) -> None:
        now = time.monotonic()
        self._warning_timestamps = [
            t for t in self._warning_timestamps
            if now - t <= self._config.warning_window
        ]

    @property
    def level(self) -> RiskLevel:
        """当前风控级别。"""
        self._prune_old_warnings()
        if self._level == RiskLevel.DANGER:
            return RiskLevel.DANGER
        if len(self._warning_timestamps) >= self._config.warning_threshold:
            return RiskLevel.DANGER
        return self._level

    def trigger_warning(self, reason: str = "") -> None:
        """记录一次预警（验证码/滑块/连续元素未找到/响应异常）。"""
        self._prune_old_warnings()
        self._warning_timestamps.append(time.monotonic())
        logger.warning("风控预警: %s (当前窗口内预警次数: %d)", reason or "未知", len(self._warning_timestamps))
        if self._on_warning:
            try:
                self._on_warning()
            except Exception as e:
                logger.exception("on_warning 回调异常: %s", e)

    def trigger_danger(self, reason: str = "") -> None:
        """直接标记为危险（session 失效、账号异常等），立即停止。"""
        self._level = RiskLevel.DANGER
        logger.error("风控危险: %s", reason or "立即停止")
        if self._on_danger:
            try:
                self._on_danger()
            except Exception as e:
                logger.exception("on_danger 回调异常: %s", e)

    def reset_to_normal(self) -> None:
        """恢复为正常（例如用户重新登录后）。"""
        self._level = RiskLevel.NORMAL
        self._warning_timestamps.clear()

    def get_warning_pause_seconds(self) -> int:
        """获取本次预警应暂停的秒数（在配置范围内随机）。"""
        lo, hi = self._config.warning_pause_range
        return random.randint(lo, hi)

    async def delay_normal(self) -> None:
        """正常操作间隔（随机）。"""
        lo, hi = self._config.normal_delay_range
        s = random.uniform(lo, hi)
        await asyncio.sleep(s)

    async def delay_page(self) -> None:
        """页面切换间隔（随机）。"""
        lo, hi = self._config.page_delay_range
        s = random.uniform(lo, hi)
        await asyncio.sleep(s)


def _sync_sleep(seconds: float) -> None:
    """同步 sleep，供非 async 场景使用。"""
    time.sleep(seconds)
