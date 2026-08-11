"""RSS/HTML 适配器单元测试（file:// fixture，不走网络）。"""

from __future__ import annotations

from pathlib import Path

from industry_intelligence.sources.html_adapter import HTMLAdapter
from industry_intelligence.sources.models import SourceItem
from industry_intelligence.sources.rss_adapter import RSSAdapter
from industry_intelligence.utils.hashing import content_hash


def _file_uri(path: Path) -> str:
    return path.as_uri()


def test_rss_discover_and_normalize(rss_fixture: Path, sample_topic: object) -> None:
    adapter = RSSAdapter({"test": _file_uri(rss_fixture)})
    items = adapter.discover(queries=[], context={})
    assert len(items) == 5
    assert items[0].source_id == "rss:test"
    assert items[0].title == "全国充电桩保有量突破500万台"
    assert items[0].published_at is not None

    raw = adapter.fetch(items[0])
    assert raw.raw_text  # 摘要非空
    parsed = adapter.parse(raw, items[0])
    assert parsed.title == items[0].title
    assert parsed.raw_type == "rss"

    doc = adapter.normalize(parsed, topic_id="t1")
    assert doc.topic_id == "t1"
    assert doc.source_id == "rss:test"
    assert doc.content_hash.startswith("crc_")
    assert doc.url_hash.startswith("url_")
    assert len(doc.document_id) == 16


def test_rss_health_check() -> None:
    assert RSSAdapter({}).health_check() is False
    assert RSSAdapter({"f": "https://example.com/feed.xml"}).health_check() is True


def test_html_extract_title_and_body(html_fixture: Path) -> None:
    adapter = HTMLAdapter()
    item = SourceItem(
        url=_file_uri(html_fixture), item_id="h1", source_id="html:test"
    )
    raw = adapter.fetch(item)
    parsed = adapter.parse(raw, item)
    assert parsed.title == "中国充电桩周报"
    assert "特来电与星星充电公布2026年充电基础设施运行数据" in parsed.content_text
    assert "导航占位" not in parsed.content_text  # nav 被剥离
    assert "页脚占位" not in parsed.content_text  # footer 被剥离
    assert "中国充电桩周报" not in parsed.content_text  # head/title 不混入正文

    doc = adapter.normalize(parsed, topic_id="t1")
    assert doc.raw_type == "html"
    assert doc.source_grade == "C"


def test_cross_adapter_content_dedup(rss_fixture: Path, html_fixture: Path) -> None:
    """RSS 某条摘要与 HTML 正文相同 → content_hash 一致（跨源内容去重）。"""
    rss = RSSAdapter({"test": _file_uri(rss_fixture)})
    html = HTMLAdapter()
    items = rss.discover(queries=[], context={})
    rss_entry = next(i for i in items if i.item_id == "example:news:5")
    rss_raw = rss.fetch(rss_entry)
    rss_parsed = rss.parse(rss_raw, rss_entry)

    html_item = SourceItem(url=_file_uri(html_fixture), item_id="h1", source_id="html:test")
    html_raw = html.fetch(html_item)
    html_parsed = html.parse(html_raw, html_item)

    assert rss_parsed.content_text == html_parsed.content_text
    assert content_hash(rss_parsed.content_text) == content_hash(html_parsed.content_text)


def test_html_same_content_different_url_dedup(
    html_fixture: Path, duplicate_html_fixture: Path
) -> None:
    """同正文、不同 URL：content_hash 相同、url_hash 不同 → 内容去重。"""
    from industry_intelligence.normalization import Deduplicator

    adapter = HTMLAdapter()
    items = [
        SourceItem(url=html_fixture.as_uri(), item_id="h1", source_id="html:a"),
        SourceItem(url=duplicate_html_fixture.as_uri(), item_id="h2", source_id="html:b"),
    ]
    docs = []
    for item in items:
        raw = adapter.fetch(item)
        docs.append(adapter.normalize(adapter.parse(raw, item), topic_id="t1"))

    assert docs[0].url_hash != docs[1].url_hash
    assert docs[0].content_hash == docs[1].content_hash

    dedup = Deduplicator()
    assert dedup.register(docs[0]) is True
    assert dedup.register(docs[1]) is False
