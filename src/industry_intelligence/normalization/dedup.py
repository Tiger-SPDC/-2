"""Layer 1 去重：URL 规范化哈希 + 内容哈希 完全匹配。"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument


class Deduplicator:
    """内存去重器，记录已见的 url_hash 与 content_hash。

    register() 返回 True 表示新文档（此前未见），False 表示重复。
    """

    def __init__(self) -> None:
        self._urls: set[str] = set()
        self._contents: set[str] = set()

    def register(self, doc: NormalizedDocument) -> bool:
        """登记文档；返回是否为新文档。"""
        if doc.url_hash in self._urls:
            return False
        if doc.content_hash in self._contents:
            return False
        self._urls.add(doc.url_hash)
        self._contents.add(doc.content_hash)
        return True

    def __len__(self) -> int:
        """当前已登记的去重 URL 数量。"""
        return len(self._urls)
