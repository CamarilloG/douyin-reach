"""
AI 筛选接口预留（M4.4）。MVP 不实现，仅定义抽象接口供后续迭代。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple


class AIProvider(ABC):
    """AI 筛选抽象接口。后续迭代实现 CloudAIProvider 对接云端大模型。"""

    @abstractmethod
    async def judge(
        self, comment: str, nickname: str, bio: str | None
    ) -> Tuple[bool, str]:
        """判断是否为目标用户。返回 (是否目标, 理由)。"""
        ...


class CloudAIProvider(AIProvider):
    """后续实现：对接云端大模型 API。"""

    def __init__(self, api_key: str, endpoint: str, model: str) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model

    async def judge(
        self, comment: str, nickname: str, bio: str | None
    ) -> Tuple[bool, str]:
        raise NotImplementedError("AI 筛选为后续迭代功能")
