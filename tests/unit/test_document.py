"""标准化文档模型单元测试。"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument, create_document_id


def _doc(**overrides: object) -> NormalizedDocument:
    base = {
        "document_id": "abc",
        "canonical_url": "https://example.com/a",
        "source_id": "rss:test",
        "title": "标题",
        "content_text": "正文",
        "content_hash": "crc_x",
        "url_hash": "url_x",
        "source_grade": "C",
        "topic_id": "t1",
    }
    base.update(overrides)
    return NormalizedDocument(**base)


def test_create_document_id_deterministic() -> None:
    a = create_document_id("https://a.com/x", "crc_1")
    b = create_document_id("https://a.com/x", "crc_1")
    c = create_document_id("https://a.com/x", "crc_2")
    assert a == b
    assert len(a) == 16
    assert a != c


def test_to_dict_roundtrip() -> None:
    doc = _doc()
    restored = NormalizedDocument.from_dict(doc.to_dict())
    assert restored == doc


def test_to_dict_optional_none() -> None:
    doc = _doc()
    d = doc.to_dict()
    assert d["published_at"] is None
    assert d["author"] is None
    assert d["matched_entities"] == []


def test_from_dict_empty_optional_normalizes() -> None:
    data = _doc().to_dict()
    data["summary"] = ""  # 空字符串应归一为 None
    doc = NormalizedDocument.from_dict(data)
    assert doc.summary is None


def test_default_fetched_at() -> None:
    doc = _doc()
    assert doc.fetched_at  # 非空
    assert "T" in doc.fetched_at
