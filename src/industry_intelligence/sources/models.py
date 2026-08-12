"""数据源相关数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utc_now_iso() -> str:
    """UTC 当前时间，ISO 8601。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class QueryPlan:
    """一条可追踪、可重复的查询计划。"""

    query_id: str
    query_string: str
    source_ids: list[str] = field(default_factory=list)
    budget: int = 10
    # 查询族：company / event / official / general（供适配器打标与预算区分）
    family: str = "general"


@dataclass
class QueryBudget:
    """查询预算上限。"""

    max_queries: int = 50
    max_per_entity: int = 3
    max_per_category: int = 5


@dataclass
class SourceItem:
    """一个待采集的数据源条目。"""

    url: str
    item_id: str
    source_id: str
    title: str | None = None
    published_at: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class RawContent:
    """抓取到的原始内容。"""

    item_id: str
    url: str
    content_type: str = "text"
    raw_text: str | None = None
    raw_bytes: bytes | None = None
    fetched_at: str = field(default_factory=_utc_now_iso)
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析后的结构化文档（normalize 的输入）。"""

    url: str
    item_id: str
    source_id: str
    title: str
    content_text: str
    raw_type: str
    published_at: str | None = None
    author: str | None = None
    language: str | None = None
    summary: str | None = None
    # 适配器元数据（如 websearch 的 family / official_domain），随标准化文档透传
    extra: dict[str, object] = field(default_factory=dict)
