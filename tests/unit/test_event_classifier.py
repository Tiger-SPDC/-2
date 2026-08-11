"""事件分类器单元测试：LLM 主路径 + 关键词回落。"""

from __future__ import annotations

from unittest import mock

import pytest

from industry_intelligence.intelligence import EventClassifier
from industry_intelligence.llm.provider import LLMError, LLMProvider

EVENT_TYPES = {
    "policy_regulation": "政策与监管",
    "bid_order": "中标/订单",
    "financing": "融资",
    "new_product": "新产品",
    "other": "其他",
}


@pytest.fixture
def mock_provider():
    provider = mock.Mock(spec=LLMProvider)
    return provider


def test_llm_classify(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {
        "event_type_id": "financing",
        "reason": "融资",
    }
    classifier = EventClassifier(
        provider=mock_provider,
        event_types=EVENT_TYPES,
        keywords=["政策", "招标"],
    )
    assert classifier.classify(make_doc()) == "financing"


def test_llm_invalid_type_falls_back_to_keyword(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {"event_type_id": "not_in_list"}
    classifier = EventClassifier(
        provider=mock_provider,
        event_types=EVENT_TYPES,
        keywords=["招标", "中标"],
    )
    doc = make_doc(title="特来电中标某省高速服务区项目")
    assert classifier.classify(doc) == "bid_order"


def test_llm_failure_falls_back_to_keyword(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.side_effect = LLMError("boom")
    classifier = EventClassifier(
        provider=mock_provider,
        event_types=EVENT_TYPES,
        keywords=["政策", "招标"],
    )
    doc = make_doc(title="国家出台充电桩补贴新政策")
    assert classifier.classify(doc) == "policy_regulation"


def test_keyword_only_path(make_doc) -> None:
    classifier = EventClassifier(event_types=EVENT_TYPES, keywords=["政策", "招标"])
    doc = make_doc(title="某地充电桩招标结果公示")
    assert classifier.classify(doc) == "bid_order"


def test_no_match_returns_other(make_doc) -> None:
    classifier = EventClassifier(event_types=EVENT_TYPES, keywords=["政策"])
    assert classifier.classify(make_doc(title="今天天气不错")) == "other"


def test_llm_sends_event_types_enum(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {"event_type_id": "other", "reason": "r"}
    classifier = EventClassifier(
        provider=mock_provider,
        event_types=EVENT_TYPES,
        keywords=[],
    )
    classifier.classify(make_doc(title="随便一条"))
    schema = mock_provider.generate_structured.call_args.args[1]
    enum = schema["properties"]["event_type_id"]["enum"]
    assert sorted(enum) == sorted(EVENT_TYPES.keys())
