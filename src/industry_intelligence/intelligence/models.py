"""情报分析数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    """聚类去重后的事件（同一事件的多篇报道合并为一条）。"""

    event_id: str
    event_type_id: str
    title: str
    event_date: str
    summary: str
    document_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    topic_id: str = ""
