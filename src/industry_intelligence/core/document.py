"""标准化文档模型。

NormalizedDocument 是全链路通用的数据货币：采集、去重、存储各层统一使用。
字段定义参考 docs/00_MASTER_PLAN.md §9。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime


def create_document_id(canonical_url: str, content_hash: str) -> str:
    """基于规范 URL 与内容哈希生成稳定的文档 ID（前 16 位 hex）。"""
    combined = f"{canonical_url}|{content_hash}".encode()
    return hashlib.sha256(combined).hexdigest()[:16]


def _utc_now_iso() -> str:
    """UTC 当前时间，ISO 8601。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class NormalizedDocument:
    """一条标准化后的文档记录。"""

    document_id: str
    canonical_url: str
    source_id: str
    title: str
    content_text: str
    content_hash: str
    url_hash: str
    source_grade: str
    topic_id: str
    fetched_at: str = field(default_factory=_utc_now_iso)
    published_at: str | None = None
    author: str | None = None
    language: str | None = None
    summary: str | None = None
    matched_entities: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    raw_type: str = "html"
    parser_version: str = "1.0"
    # 适配器元数据（如 websearch 的 family / official_domain），供 JSONL/SQLite 追溯
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """序列化为可 JSON 化的 dict（JSONL 写入）。"""
        return {
            "document_id": self.document_id,
            "canonical_url": self.canonical_url,
            "source_id": self.source_id,
            "title": self.title,
            "content_text": self.content_text,
            "content_hash": self.content_hash,
            "url_hash": self.url_hash,
            "source_grade": self.source_grade,
            "topic_id": self.topic_id,
            "fetched_at": self.fetched_at,
            "published_at": self.published_at,
            "author": self.author,
            "language": self.language,
            "summary": self.summary,
            "matched_entities": self.matched_entities,
            "matched_keywords": self.matched_keywords,
            "raw_type": self.raw_type,
            "parser_version": self.parser_version,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> NormalizedDocument:
        """从 JSON 解析的 dict 反序列化（JSONL 读取）。"""
        return cls(
            document_id=str(data["document_id"]),
            canonical_url=str(data["canonical_url"]),
            source_id=str(data["source_id"]),
            title=str(data["title"]),
            content_text=str(data["content_text"]),
            content_hash=str(data["content_hash"]),
            url_hash=str(data["url_hash"]),
            source_grade=str(data["source_grade"]),
            topic_id=str(data["topic_id"]),
            fetched_at=str(data["fetched_at"]),
            published_at=_opt_str(data.get("published_at")),
            author=_opt_str(data.get("author")),
            language=_opt_str(data.get("language")),
            summary=_opt_str(data.get("summary")),
            matched_entities=_opt_str_list(data.get("matched_entities")),
            matched_keywords=_opt_str_list(data.get("matched_keywords")),
            raw_type=str(data.get("raw_type", "html")),
            parser_version=str(data.get("parser_version", "1.0")),
            extra=_opt_dict(data.get("extra")),
        )


def _opt_str(value: object | None) -> str | None:
    """空值/None 归一为 None，其余转 str。"""
    if value is None or value == "":
        return None
    return str(value)


def _opt_dict(value: object | None) -> dict[str, object]:
    """JSON 反序列化的 extra 字段安全转 dict。"""
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items()}


def _opt_str_list(value: object | None) -> list[str]:
    """JSON 反序列化的列表字段安全转 str 列表。"""
    if not isinstance(value, list):
        return []
    return [str(x) for x in value]
