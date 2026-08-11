"""配置数据模型单元测试。"""

from __future__ import annotations

from industry_intelligence.config.models import (
    CollectionConfig,
    CompanyEntity,
    LLMConfig,
    SystemConfig,
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


def test_llm_config_defaults() -> None:
    cfg = LLMConfig()
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.api_key_env == "DEEPSEEK_API_KEY"
    assert cfg.base_url == "https://api.deepseek.com/v1"
    assert cfg.temperature == 0.1
    assert cfg.max_tokens == 4096


def test_system_config_has_llm_default() -> None:
    sys_cfg = SystemConfig()
    assert sys_cfg.llm.provider == "deepseek"
    assert sys_cfg.llm.api_key_env == "DEEPSEEK_API_KEY"
