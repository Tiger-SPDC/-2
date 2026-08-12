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


def test_official_domain_family(sample_topic: object) -> None:
    """官方站点族：核心词 × official_domains → "核心词 site:域名"，family=official。"""
    topic = _topic_with_official_domains(sample_topic)  # type: ignore[arg-type]
    plans = SearchPlanner().generate_plans(topic, _minimal_task())  # type: ignore[arg-type]
    official = [p for p in plans if p.family == "official"]
    queries = [p.query_string for p in official]
    assert "充电桩 site:gov.cn" in queries
    assert "充电桩 site:nea.gov.cn" in queries
    assert "充电基础设施 site:gov.cn" in queries
    assert all("site:" in q for q in queries)
    assert all(p.family == "official" for p in official)
    # 通用族不受影响
    assert any(p.family == "company" for p in plans)
    assert any(p.family == "event" for p in plans)


def test_official_family_empty_without_domains(
    sample_topic: object, sample_task: object
) -> None:
    plans = SearchPlanner().generate_plans(sample_topic, sample_task)  # type: ignore[arg-type]
    assert not any(p.family == "official" for p in plans)


def test_official_family_respects_per_category_budget(sample_topic: object) -> None:
    topic = _topic_with_official_domains(sample_topic)  # type: ignore[arg-type]
    planner = SearchPlanner(QueryBudget(max_per_category=1))
    plans = planner.generate_plans(topic, _minimal_task())  # type: ignore[arg-type]
    official = [p for p in plans if p.family == "official"]
    # 每个域名只取第 1 个核心词（2 个域名 → 2 条查询）
    assert len(official) == 2
    assert sorted(p.query_string for p in official) == [
        "充电桩 site:gov.cn",
        "充电桩 site:nea.gov.cn",
    ]
    # 每个域名第 2 个核心词被截断
    assert not any("充电基础设施 site:" in p.query_string for p in official)


def test_official_family_respects_total_budget(sample_topic: object) -> None:
    topic = _topic_with_official_domains(sample_topic)  # type: ignore[arg-type]
    planner = SearchPlanner(QueryBudget(max_queries=3))
    plans = planner.generate_plans(topic, _minimal_task())  # type: ignore[arg-type]
    assert len(plans) == 3
    # 企业/事件族优先（通用覆盖优先），official 族占用剩余预算
    assert plans[0].family == "company"


def _topic_with_official_domains(topic: object):
    """在 sample_topic 基础上附加官方站点域名。"""
    import dataclasses

    return dataclasses.replace(
        topic, official_domains=["gov.cn", "nea.gov.cn"]  # type: ignore[arg-type]
    )


def _minimal_task() -> TaskConfig:
    return TaskConfig(id="tk_official", topic_id="t1", enabled=True)
