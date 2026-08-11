"""数据源适配器：Search/RSS/HTML/API/PDF 等可插拔 Adapter。"""

from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.html_adapter import HTMLAdapter
from industry_intelligence.sources.models import (
    ParsedDocument,
    QueryBudget,
    QueryPlan,
    RawContent,
    SourceItem,
)
from industry_intelligence.sources.rss_adapter import RSSAdapter

__all__ = [
    "HTMLAdapter",
    "ParsedDocument",
    "QueryBudget",
    "QueryPlan",
    "RawContent",
    "RSSAdapter",
    "SourceAdapter",
    "SourceItem",
]
