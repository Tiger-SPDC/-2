"""URL 与正文内容的确定性哈希。

前缀 url_ / crc_ 用于区分两种哈希命名空间，并在 JSONL 中自解释。
"""

from __future__ import annotations

import hashlib

from industry_intelligence.utils.url import canonicalize_url


def url_hash(url: str) -> str:
    """对规范化后的 URL 取 sha256，前缀 url_。"""
    canonical = canonicalize_url(url)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"url_{digest}"


def content_hash(text: str) -> str:
    """对正文做空白归一化后取 sha256，前缀 crc_。

    空白归一化保证同一正文的不同排版（多空格/换行）得到相同指纹。
    """
    normalized = " ".join(text.split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"crc_{digest}"
