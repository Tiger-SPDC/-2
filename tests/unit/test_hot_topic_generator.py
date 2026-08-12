"""HotTopicGenerator 单元测试：LLM 动态热点发现。"""

from __future__ import annotations

from unittest import mock

from industry_intelligence.intelligence.hot_topics import (
    HOT_TOPICS_SCHEMA,
    HotTopicGenerator,
    _parse_topics,
)
from industry_intelligence.llm.provider import LLMError, LLMProvider


def _generator(provider=None, template: str = "") -> HotTopicGenerator:
    return HotTopicGenerator(provider=provider, prompt_template=template)


def test_no_provider_returns_empty(sample_topic) -> None:
    assert _generator(provider=None).generate(sample_topic) == []


def test_llm_error_returns_empty(sample_topic) -> None:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    assert _generator(provider=provider).generate(sample_topic) == []


def test_parses_dedupes_and_caps(sample_topic) -> None:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "topics": ["液冷超充 800V", "液冷超充 800V", "  ", "发改委 充电基础设施 政策"]
    }
    topics = _generator(provider=provider).generate(sample_topic, max_topics=2)
    assert topics == ["液冷超充 800V", "发改委 充电基础设施 政策"]
    # 去重 + 空串过滤后仅 2 条，未超上限
    provider.generate_structured.return_value = {
        "topics": ["a", "b", "c"]
    }
    assert _generator(provider=provider).generate(sample_topic, max_topics=2) == ["a", "b"]


def test_invalid_shapes_return_empty(sample_topic) -> None:
    provider = mock.Mock(spec=LLMProvider)
    for raw in (
        {"topics": "not-a-list"},
        {},
        {"topics": [123, None]},
        {"topics": ["", "  "]},
    ):
        provider.generate_structured.return_value = raw
        assert _generator(provider=provider).generate(sample_topic) == []


def test_schema_contains_topics_array(sample_topic) -> None:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"topics": ["x"]}
    _generator(provider=provider).generate(sample_topic)
    schema = provider.generate_structured.call_args.args[1]
    assert schema == HOT_TOPICS_SCHEMA
    assert schema["properties"]["topics"]["type"] == "array"


def test_prompt_contains_core_and_focus_override(sample_topic) -> None:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"topics": ["x"]}
    gen = _generator(provider=provider)
    # 默认使用 core
    gen.generate(sample_topic)
    prompt = provider.generate_structured.call_args.args[0]
    assert "充电桩" in prompt
    assert "特来电" in prompt
    assert "中国" in prompt
    # focus 覆盖 core
    gen.generate(sample_topic, focus=["换电"])
    prompt = provider.generate_structured.call_args.args[0]
    assert "换电" in prompt


def test_parse_topics_unit() -> None:
    assert _parse_topics({"topics": ["a", " a ", "b", "a"]}, 10) == ["a", "b"]
    assert _parse_topics({"topics": "x"}, 10) == []
    assert _parse_topics({}, 10) == []
    assert _parse_topics({"topics": ["a", "b", "c"]}, 2) == ["a", "b"]
