"""JSONL 追加式存储。

一行一个 JSON 文档（ensure_ascii=False，排序键），每次 append 立即 flush。
Phase 1 数据量小，查询采用线性扫描。
"""

from __future__ import annotations

import json
from pathlib import Path

from industry_intelligence.core.document import NormalizedDocument


class JSONLStore:
    """追加式 JSONL 存储。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, doc: NormalizedDocument) -> None:
        """追加一条文档并立即 flush。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(doc.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()

    def read_all(self) -> list[NormalizedDocument]:
        """读取全部文档。"""
        if not self._path.exists():
            return []
        docs: list[NormalizedDocument] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                docs.append(NormalizedDocument.from_dict(json.loads(line)))
        return docs

    def query_by_hash(self, content_hash: str) -> list[NormalizedDocument]:
        """按内容哈希线性扫描查询。"""
        return [d for d in self.read_all() if d.content_hash == content_hash]

    def count(self) -> int:
        """当前文档总数。"""
        return len(self.read_all())
