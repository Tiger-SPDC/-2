"""事件聚类：同事件多篇报道合并为一条 Event（L2/L3 去重）。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.intelligence.models import Event


class EventClusterer:
    """按标题相似度 + 共享实体 + 时间接近合并文档。

    三条件须全部满足才合并；同一连通分量内任意文档间满足即归并
    （避免贪心比较首文档造成的漏并）。
    """

    def __init__(self, similarity_threshold: float = 0.6, max_gap_days: int = 3) -> None:
        self._threshold = similarity_threshold
        self._max_gap_days = max_gap_days

    def cluster(
        self,
        docs: list[NormalizedDocument],
        doc_event_types: Mapping[str, str] | None = None,
    ) -> list[Event]:
        """将文档列表聚为事件列表（每篇文档恰好归属一个 Event）。"""
        if not docs:
            return []
        types = dict(doc_event_types) if doc_event_types else {}
        parent = list(range(len(docs)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                if self._should_merge(docs[i], docs[j]):
                    union(i, j)

        groups: dict[int, list[NormalizedDocument]] = {}
        for i, doc in enumerate(docs):
            groups.setdefault(find(i), []).append(doc)

        events = [self._make_event(group, types) for group in groups.values()]
        return sorted(events, key=lambda e: (e.event_date, e.title))

    def _should_merge(self, a: NormalizedDocument, b: NormalizedDocument) -> bool:
        return (
            self._title_similarity(a, b) >= self._threshold
            and self._has_shared_entities(a, b)
            and self._close_in_time(a, b)
        )

    def _title_similarity(self, a: NormalizedDocument, b: NormalizedDocument) -> float:
        ta, tb = a.title.strip(), b.title.strip()
        if not ta or not tb:
            return 0.0
        return SequenceMatcher(None, ta, tb).ratio()

    def _has_shared_entities(self, a: NormalizedDocument, b: NormalizedDocument) -> bool:
        return bool(set(a.matched_entities) & set(b.matched_entities))

    def _close_in_time(self, a: NormalizedDocument, b: NormalizedDocument) -> bool:
        if not a.published_at or not b.published_at:
            return False
        try:
            ta = datetime.fromisoformat(a.published_at)
            tb = datetime.fromisoformat(b.published_at)
        except ValueError:
            return False
        gap = abs(ta - tb)
        return gap <= timedelta(days=self._max_gap_days)

    def _make_event(
        self, group: list[NormalizedDocument], types: dict[str, str]
    ) -> Event:
        ordered = sorted(group, key=lambda d: d.published_at or d.fetched_at)
        first = ordered[0]
        event_id = hashlib.sha256(first.title.strip().encode()).hexdigest()[:16]
        summary = max((d.content_text for d in group), key=len)
        return Event(
            event_id=event_id,
            event_type_id=types.get(first.document_id, "other"),
            title=first.title,
            event_date=first.published_at or first.fetched_at,
            summary=summary,
            document_ids=[d.document_id for d in ordered],
            entity_ids=sorted({e for d in group for e in d.matched_entities}),
            # 置信度随佐证文档数上升：单篇 0.6，每增一篇 +0.1，封顶 1.0
            confidence=min(1.0, 0.5 + 0.1 * len(group)),
            topic_id=first.topic_id,
        )
