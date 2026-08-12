"""多适配器聚合：discover 聚合去重，fetch/parse/normalize 按 source_id 前缀路由。

用于把 RSS 基线 + 网页搜索等适配器聚合为一个整体，向 Pipeline 暴露统一 SourceAdapter，
并在 websearch 禁用/失败时自动回退 RSS-only（health_check = 任一子适配器健康）。
"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.models import (
    ParsedDocument,
    QueryPlan,
    RawContent,
    SourceItem,
)
from industry_intelligence.utils.url import canonicalize_url


class CompositeAdapter(SourceAdapter):
    """聚合多个子适配器；按 source_id 前缀路由到对应子适配器。"""

    source_id = "composite"
    source_grade = "C"

    def __init__(self, adapters: list[SourceAdapter] | None = None) -> None:
        self._adapters = list(adapters or [])

    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        """聚合各子适配器的发现结果，跨源 URL 去重。"""
        seen: set[str] = set()
        items: list[SourceItem] = []
        for sub in self._adapters:
            for item in sub.discover(queries, context):
                canonical = canonicalize_url(item.url)
                if canonical in seen:
                    continue
                seen.add(canonical)
                items.append(item)
        return items

    def fetch(self, item: SourceItem) -> RawContent:
        return self._route(item).fetch(item)

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        return self._route(item).parse(raw, item)

    def normalize(
        self, parsed: ParsedDocument, topic_id: str
    ) -> NormalizedDocument:
        return self._route(parsed).normalize(parsed, topic_id)

    def health_check(self) -> bool:
        return any(sub.health_check() for sub in self._adapters)

    def _route(self, item: SourceItem | ParsedDocument) -> SourceAdapter:
        """按 source_id 前缀匹配子适配器（如 websearch:bing -> websearch）。"""
        source_id = item.source_id
        for sub in self._adapters:
            if source_id == sub.source_id or source_id.startswith(f"{sub.source_id}:"):
                return sub
        raise ValueError(f"no adapter for source_id {source_id!r}")
