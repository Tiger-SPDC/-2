"""通知 Adapter 抽象层（Phase 4）：推送通道可替换，核心系统不感知具体通道。

推送失败是"尽力而为"——失败仅记录结果，不影响已生成的报告。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NotificationResult:
    """一次通知发送的结果。"""

    success: bool
    retry_count: int = 0
    error: str | None = None


class NotificationAdapter(ABC):
    """通知通道抽象基类。

    实现约定：
    - :meth:`send` 发送通知，成功返回 True；
    - 失败返回 ``NotificationResult(success=False, error=...)``，不抛出异常；
    - ``channel_name`` 标识通道（用于日志）。
    """

    channel_name: str = "unknown"

    @abstractmethod
    def send(self, title: str, content: str) -> NotificationResult:
        """发送通知；推送失败不抛出，返回 NotificationResult。"""
