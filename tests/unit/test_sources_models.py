"""数据源模型单元测试。"""

from __future__ import annotations

from industry_intelligence.sources.models import (
    QueryBudget,
    QueryPlan,
    RawContent,
    SourceItem,
)


def test_query_plan_defaults() -> None:
    plan = QueryPlan(query_id="q1", query_string="充电桩")
    assert plan.source_ids == []
    assert plan.budget == 10


def test_source_item_defaults() -> None:
    item = SourceItem(url="https://a.com", item_id="i1", source_id="rss:f")
    assert item.title is None
    assert item.published_at is None
    assert item.extra == {}


def test_raw_content_fetched_at_default() -> None:
    raw = RawContent(item_id="i1", url="https://a.com")
    assert raw.fetched_at
    assert raw.status_code == 200
    assert raw.content_type == "text"


def test_query_budget_defaults() -> None:
    b = QueryBudget()
    assert b.max_queries == 50
    assert b.max_per_entity == 3
    assert b.max_per_category == 5
