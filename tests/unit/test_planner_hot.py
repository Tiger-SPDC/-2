"""SearchPlanner 热点族测试：热点优先、空回退三族。"""

from __future__ import annotations

import dataclasses

from industry_intelligence.collectors.planner import SearchPlanner
from industry_intelligence.config.models import TaskConfig, TaskOverrides
from industry_intelligence.sources.models import QueryBudget

HOT = ["液冷超充 800V", "发改委 充电基础设施 政策", "车网互动 V2G"]


def test_hot_topics_use_hot_family_only(sample_topic, sample_task) -> None:
    plans = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=HOT)
    assert plans
    assert all(p.family == "hot" for p in plans)
    queries = [p.query_string for p in plans]
    assert "液冷超充 800V 中国" in queries
    assert "发改委 充电基础设施 政策 中国" in queries
    # 热点优先：不再出现固定企业/事件词查询
    assert "特来电" not in " ".join(queries)
    assert "政策" not in " ".join(queries).replace("充电基础设施 政策", "")
    assert len(plans) == len(set(queries))


def test_hot_topics_count_is_phrase_x_region(sample_topic, sample_task) -> None:
    plans = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=HOT)
    # 3 热点 × 1 地区（中国）
    assert len(plans) == 3


def test_hot_topics_respects_region_override(sample_topic) -> None:
    task = TaskConfig(
        id="tk_hot", topic_id="t1", enabled=True,
        overrides=TaskOverrides(regions=["长三角"], focus=["换电"]),
    )
    plans = SearchPlanner().generate_plans(sample_topic, task, hot_topics=HOT)
    queries = [p.query_string for p in plans]
    assert all("长三角" in q for q in queries)
    assert "液冷超充 800V 长三角" in queries


def test_empty_hot_topics_falls_back_to_legacy(
    sample_topic, sample_task
) -> None:
    plans = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=[])
    queries = [p.query_string for p in plans]
    # 空热点 → 回退固定企业/事件族
    assert any(p.family == "company" for p in plans)
    assert any(p.family == "event" for p in plans)
    assert not any(p.family == "hot" for p in plans)
    assert "充电桩 特来电 中国" in queries


def test_none_hot_topics_keeps_legacy(sample_topic, sample_task) -> None:
    with_hot = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=None)
    without_hot = SearchPlanner().generate_plans(sample_topic, sample_task)
    assert [p.query_string for p in with_hot] == [p.query_string for p in without_hot]


def test_hot_max_budget_truncates(sample_topic, sample_task) -> None:
    planner = SearchPlanner(QueryBudget(max_hot=2))
    plans = planner.generate_plans(sample_topic, sample_task, hot_topics=HOT)
    queries = [p.query_string for p in plans]
    assert len(queries) == 2
    assert "液冷超充 800V 中国" in queries
    assert "车网互动 V2G 中国" not in queries  # 第 3 条热点被截断


def test_hot_respects_total_query_budget(sample_topic, sample_task) -> None:
    planner = SearchPlanner(QueryBudget(max_queries=2))
    plans = planner.generate_plans(sample_topic, sample_task, hot_topics=HOT)
    assert len(plans) == 2
    assert all(p.family == "hot" for p in plans)


def test_hot_with_empty_regions_falls_back_safely(sample_topic) -> None:
    task = TaskConfig(
        id="tk_hot_no_region", topic_id="t1", enabled=True,
        overrides=TaskOverrides(regions=[]),
    )
    plans = SearchPlanner().generate_plans(sample_topic, task, hot_topics=HOT)
    # 热点组合为空（地区空）→ 回退三族同样为空，不抛错
    assert plans == []


def test_hot_query_id_fingerprint_stable(sample_topic, sample_task) -> None:
    a = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=HOT)
    b = SearchPlanner().generate_plans(sample_topic, sample_task, hot_topics=HOT)
    assert [p.query_id for p in a] == [p.query_id for p in b]


def test_hot_with_official_domains_still_hot_only(sample_topic, sample_task) -> None:
    topic = dataclasses.replace(
        sample_topic, official_domains=["gov.cn"]  # type: ignore[arg-type]
    )
    plans = SearchPlanner().generate_plans(topic, sample_task, hot_topics=HOT)
    assert all(p.family == "hot" for p in plans)
    assert not any("site:" in p.query_string for p in plans)
