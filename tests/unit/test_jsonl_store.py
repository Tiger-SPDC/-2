"""JSONL 存储单元测试。"""

from __future__ import annotations

from pathlib import Path

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.storage import JSONLStore
from industry_intelligence.utils.hashing import content_hash, url_hash


def _doc(url: str, text: str, doc_id: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_id=doc_id,
        canonical_url=url,
        source_id="s",
        title="T",
        content_text=text,
        content_hash=content_hash(text),
        url_hash=url_hash(url),
        source_grade="C",
        topic_id="t1",
    )


def test_append_and_count(tmp_path: Path) -> None:
    store = JSONLStore(tmp_path / "nested" / "out.jsonl")
    store.append(_doc("https://a.com/x", "正文", "d1"))
    store.append(_doc("https://b.com/y", "其他", "d2"))
    assert store.count() == 2
    assert (tmp_path / "nested" / "out.jsonl").exists()  # 父目录自动创建


def test_read_all_roundtrip(tmp_path: Path) -> None:
    store = JSONLStore(tmp_path / "out.jsonl")
    doc = _doc("https://a.com/x", "正文", "d1")
    store.append(doc)
    restored = store.read_all()
    assert len(restored) == 1
    assert restored[0] == doc
    assert restored[0].to_dict() == doc.to_dict()


def test_query_by_hash(tmp_path: Path) -> None:
    store = JSONLStore(tmp_path / "out.jsonl")
    store.append(_doc("https://a.com/x", "重复正文", "d1"))
    store.append(_doc("https://b.com/y", "重复正文", "d2"))
    hits = store.query_by_hash(content_hash("重复正文"))
    assert len(hits) == 2
    assert store.query_by_hash(content_hash("不存在")) == []


def test_missing_file_reads_empty(tmp_path: Path) -> None:
    store = JSONLStore(tmp_path / "absent.jsonl")
    assert store.read_all() == []
    assert store.count() == 0


def test_append_is_append_only(tmp_path: Path) -> None:
    store = JSONLStore(tmp_path / "out.jsonl")
    store.append(_doc("https://a.com/x", "正文", "d1"))
    store.append(_doc("https://a.com/x", "正文", "d1"))  # 存储层不拒绝重复
    assert store.count() == 2
