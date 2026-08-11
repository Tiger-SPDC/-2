"""配置数据模型单元测试。"""

from __future__ import annotations

from industry_intelligence.config.models import (
    CollectionConfig,
    CompanyEntity,
    TaskOverrides,
    TaskWindow,
    TopicKeywords,
)


def test_collection_defaults() -> None:
    cfg = CollectionConfig()
    assert cfg.max_concurrency == 5
    assert cfg.request_timeout_seconds == 20
    assert cfg.polite_delay_seconds == 1.5


def test_topic_keywords_defaults() -> None:
    kw = TopicKeywords()
    assert kw.core == []
    assert kw.events == []
    assert kw.exclude == []


def test_company_entity_defaults() -> None:
    c = CompanyEntity(canonical_name="特来电")
    assert c.aliases == []
    assert c.priority == 1


def test_task_overrides_none_by_default() -> None:
    ov = TaskOverrides()
    assert ov.regions is None
    assert ov.companies is None
    assert ov.focus is None


def test_task_window_defaults() -> None:
    w = TaskWindow()
    assert w.type == "rolling"
    assert w.days == 7
