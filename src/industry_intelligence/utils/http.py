"""HTTP / file 文本读取工具。

适配器共用；支持 http/https 与 file://（离线测试用）。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import requests


def fetch_text(
    url: str,
    timeout: int = 20,
    user_agent: str = "industry-intelligence-agent",
    max_bytes: int = 5_000_000,
) -> str | None:
    """读取 URL 文本内容；任一步失败返回 None（不抛出）。

    - http/https：requests GET，带超时与 User-Agent
    - file://：直接读取本地文件（用于离线测试）
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            filepath = url2pathname(parsed.path)
            return Path(filepath).read_text(encoding="utf-8", errors="replace")
        if parsed.scheme in ("http", "https"):
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
            resp.raise_for_status()
            return resp.text[:max_bytes]
        return None
    except (OSError, requests.RequestException):
        return None
