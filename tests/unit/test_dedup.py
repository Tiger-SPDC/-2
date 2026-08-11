"""Layer 1 去重器单元测试。"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.normalization import Deduplicator
from industry_intelligence.utils.hashing import content_hash, url_hash


def _doc(url: str, text: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_id="d",
        canonical_url=url,
        source_id="s",
        title="T",
        content_text=text,
        content_hash=content_hash(text),
        url_hash=url_hash(url),
        source_grade="C",
        topic_id="t1",
    )


def test_new_document_registered() -> None:
    dedup = Deduplicator()
    assert dedup.register(_doc("https://a.com/x", "正文")) is True
    assert len(dedup) == 1


def test_same_url_rejected() -> None:
    dedup = Deduplicator()
    dedup.register(_doc("https://a.com/x", "正文"))
    assert dedup.register(_doc("https://a.com/x", "其他正文")) is False  # URL 重复


def test_same_content_rejected() -> None:
    dedup = Deduplicator()
    dedup.register(_doc("https://a.com/x", "同一正文"))
    assert dedup.register(_doc("https://b.com/y", "同一正文")) is False  # 内容重复


def test_distinct_docs_accepted() -> None:
    dedup = Deduplicator()
    assert dedup.register(_doc("https://a.com/x", "甲")) is True
    assert dedup.register(_doc("https://b.com/y", "乙")) is True
    assert len(dedup) == 2
