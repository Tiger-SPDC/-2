"""搜索计划生成器单元测试。"""

from __future__ import annotations

from industry_intelligence.collectors.planner import SearchPlanner
from industry_intelligence.config.models import TaskConfig, TaskOverrides
from industry_intelligence.sources.models import QueryBudget


def test_company_and_event_families(sample_topic: object, sample_task: object) -> None:
    """核心词×企业×地区 + 核心词×事件词×地区。"""
    plans = SearchPlanner().generate_plans(sample_topic, sample_task)  # type: ignore[arg-type]
    queries = [p.query_string for p in plans]
    assert "充电桩 特来电 中国" in queries
    assert "充电基础设施 星星充电 中国" in queries
    assert "充电桩 政策 中国" in queries
    assert "充电桩 招标 中国" in queries
    assert len(plans) == len(set(queries))  # 同次运行内无重复


def test_query_id_fingerprint_stable(sample_topic: object, sample_task: object) -> None:
    a = SearchPlanner().generate_plans(sample_topic, sample_task)  # type: ignore[arg-type]
    b = SearchPlanner().generate_plans(sample_topic, sample_task)  # type: ignore[arg-type]
    assert [p.query_id for p in a] == [p.query_id for p in b]


def test_overrides_replace_defaults(sample_topic: object) -> None:
    """overrides 只影响企业族；事件族仍使用事件词（不受 companies override 影响）。"""
    task = TaskConfig(
        id="tk2",
        topic_id="t1",
        enabled=True,
        overrides=TaskOverrides(regions=["长三角"], companies=["特来电"], focus=["超充"]),
    )
    plans = SearchPlanner().generate_plans(sample_topic, task)  # type: ignore[arg-type]
    queries = [p.query_string for p in plans]
    assert "超充 特来电 长三角" in queries
    assert "星星充电" not in " ".join(queries)  # 企业 override 生效
    assert "超充 政策 长三角" in queries
    assert "超充 招标 长三角" in queries
    assert all("长三角" in q for q in queries)  # 地区 override 生效


def test_disabled_task_returns_empty(sample_topic: object) -> None:
    task = TaskConfig(id="tk3", topic_id="t1", enabled=False)
    assert SearchPlanner().generate_plans(sample_topic, task) == []  # type: ignore[arg-type]


def test_budget_max_queries_cap(sample_topic: object, sample_task: object) -> None:
    planner = SearchPlanner(QueryBudget(max_queries=2))
    plans = planner.generate_plans(sample_topic, sample_task)  # type: ignore[arg-type]
    assert len(plans) == 2
