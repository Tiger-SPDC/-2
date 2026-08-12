"""CompositeAdapter 单元测试：聚合去重与 source_id 前缀路由（全离线）。"""

from __future__ import annotations

import pytest

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.composite_adapter import CompositeAdapter
from industry_intelligence.sources.models import (
    ParsedDocument,
    QueryPlan,
    RawContent,
    SourceItem,
)


class _FakeAdapter(SourceAdapter):
    """可记录路由的最小适配器。"""

    def __init__(
        self, source_id: str, urls: list[str], healthy: bool = True
    ) -> None:
        self.source_id = source_id
        self.source_grade = "C"
        self._urls = urls
        self._healthy = healthy
        self.route_calls: list[str] = []

    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        return [
            SourceItem(
                url=url,
                item_id=f"it_{self.source_id}_{idx}",
                source_id=f"{self.source_id}:sub",
            )
            for idx, url in enumerate(self._urls)
        ]

    def fetch(self, item: SourceItem) -> RawContent:
        self.route_calls.append(f"fetch:{item.source_id}")
        return RawContent(item_id=item.item_id, url=item.url)

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        return ParsedDocument(
            url=item.url,
            item_id=item.item_id,
            source_id=item.source_id,
            title="T",
            content_text="C",
            raw_type="html",
        )

    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        from industry_intelligence.utils.hashing import content_hash, url_hash

        return NormalizedDocument(
            document_id=f"d_{parsed.source_id}",
            canonical_url=parsed.url,
            source_id=parsed.source_id,
            title=parsed.title,
            content_text=parsed.content_text,
            content_hash=content_hash(parsed.content_text),
            url_hash=url_hash(parsed.url),
            source_grade="C",
            topic_id=topic_id,
            raw_type=parsed.raw_type,
        )

    def health_check(self) -> bool:
        return self._healthy


def _plan(q: str = "q") -> QueryPlan:
    return QueryPlan(query_id="qid1", query_string=q)


def test_discover_aggregates_and_dedups() -> None:
    rss = _FakeAdapter("rss", ["https://x.com/a", "https://x.com/b"])
    web = _FakeAdapter("websearch", ["https://x.com/b", "https://x.com/c"])
    composite = CompositeAdapter([rss, web])
    items = composite.discover([_plan()], context={})
    urls = [i.url for i in items]
    assert urls == ["https://x.com/a", "https://x.com/b", "https://x.com/c"]
    assert len(urls) == len(set(urls))


def test_route_fetch_by_source_id_prefix() -> None:
    rss = _FakeAdapter("rss", [])
    web = _FakeAdapter("websearch", [])
    composite = CompositeAdapter([rss, web])
    item = SourceItem(
        url="https://x.com/a",
        item_id="it1",
        source_id="websearch:bing",
    )
    composite.fetch(item)
    assert web.route_calls == ["fetch:websearch:bing"]
    assert rss.route_calls == []


def test_route_exact_source_id_matches() -> None:
    rss = _FakeAdapter("rss", [])
    composite = CompositeAdapter([rss])
    item = SourceItem(url="https://x.com/r", item_id="it2", source_id="rss")
    composite.fetch(item)
    assert rss.route_calls == ["fetch:rss"]


def test_route_unknown_source_id_raises() -> None:
    composite = CompositeAdapter([_FakeAdapter("rss", [])])
    item = SourceItem(url="https://x.com/x", item_id="it3", source_id="unknown:foo")
    with pytest.raises(ValueError, match="unknown:foo"):
        composite.fetch(item)


def test_health_check_any_healthy() -> None:
    assert CompositeAdapter([_FakeAdapter("rss", [], healthy=False)]).health_check() is False
    assert (
        CompositeAdapter(
            [_FakeAdapter("rss", [], healthy=False), _FakeAdapter("websearch", [])]
        ).health_check()
        is True
    )
    assert CompositeAdapter([]).health_check() is False


def test_empty_composite_discover() -> None:
    assert CompositeAdapter([]).discover([_plan()], context={}) == []
