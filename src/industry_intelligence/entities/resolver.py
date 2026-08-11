"""实体解析：文档文本 ↔ Topic 企业实体（canonical_name + aliases）。

索引与匹配全部来自 TopicProfile 配置，核心代码不硬编码企业名。
"""

from __future__ import annotations

from dataclasses import dataclass

from industry_intelligence.config.models import TopicProfile
from industry_intelligence.core.document import NormalizedDocument


@dataclass(frozen=True)
class EntityMatch:
    """文本中命中一个实体。"""

    canonical_name: str
    matched_term: str
    priority: int = 1


class EntityResolver:
    """基于 Topic 企业实体构建的 casefold 索引解析器。"""

    def __init__(self, topic: TopicProfile) -> None:
        self._index: dict[str, EntityMatch] = {}
        for company in topic.entities.companies:
            for term in (company.canonical_name, *company.aliases):
                term = term.strip()
                if not term:
                    continue
                # setdefault：先声明者优先，不覆盖
                self._index.setdefault(
                    term.casefold(),
                    EntityMatch(
                        canonical_name=company.canonical_name,
                        matched_term=term,
                        priority=company.priority,
                    ),
                )

    def resolve(self, text: str) -> list[EntityMatch]:
        """在文本中查找命中实体；同一实体命中多个词条时取最长者。"""
        if not text:
            return []
        folded = text.casefold()
        best: dict[str, EntityMatch] = {}
        for term, match in self._index.items():
            if term in folded:
                current = best.get(match.canonical_name)
                if current is None or len(match.matched_term) > len(current.matched_term):
                    best[match.canonical_name] = match
        return sorted(best.values(), key=lambda m: (m.priority, m.canonical_name))

    def resolve_document(self, doc: NormalizedDocument) -> NormalizedDocument:
        """扫描标题与正文，填充 ``matched_entities`` 后返回同一文档。"""
        text = "\n".join(part for part in (doc.title, doc.content_text) if part)
        doc.matched_entities = [m.canonical_name for m in self.resolve(text)]
        return doc
