"""Server酱（方糖）通知 Adapter（Phase 4，§21.1）。

SendKey 通过环境变量注入（config notification.serverchan_key_env），Secret 不落库、
不提交 Git。内置重试；推送失败返回 NotificationResult，不抛出、不影响报告生成。
"""

from __future__ import annotations

import logging
import time

import requests

from industry_intelligence.notification.adapter import (
    NotificationAdapter,
    NotificationResult,
)

logger = logging.getLogger(__name__)

#: Server酱 API 单条消息长度限制（desp），超出截断
_MAX_CONTENT_CHARS = 4000

_DEFAULT_TIMEOUT_SECONDS = 10


class ServerChanAdapter(NotificationAdapter):
    """通过 Server酱 HTTP API 推送微信消息。"""

    channel_name = "serverchan"

    def __init__(
        self,
        sendkey: str | None,
        retry: int = 2,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._sendkey = sendkey
        self._retry = max(retry, 0)
        self._timeout = timeout_seconds

    def send(self, title: str, content: str) -> NotificationResult:
        """POST https://sctapi.ftqq.com/{key}.send；失败重试，不抛出。"""
        if not self._sendkey:
            return NotificationResult(
                success=False,
                retry_count=0,
                error="ServerChan sendkey not configured",
            )
        payload = {
            "title": title,
            "desp": content[:_MAX_CONTENT_CHARS],
        }
        last_error: str | None = None
        attempts = 0
        for attempt in range(self._retry + 1):
            attempts += 1
            try:
                resp = requests.post(
                    f"https://sctapi.ftqq.com/{self._sendkey}.send",
                    data=payload,
                    timeout=self._timeout,
                )
                if resp.ok:
                    return NotificationResult(success=True, retry_count=attempts)
                last_error = f"ServerChan HTTP {resp.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            if attempt < self._retry:
                time.sleep(1.0)
        return NotificationResult(
            success=False,
            retry_count=attempts,
            error=last_error,
        )
