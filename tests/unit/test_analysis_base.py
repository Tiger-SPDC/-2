"""分析 Agent 基类单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from industry_intelligence.analysis.base import AnalysisAgent
from industry_intelligence.analysis.historical import (
    WINDOW_CURRENT,
    WINDOW_LAST,
    WINDOW_LAST_4W,
    WINDOW_LAST_12W,
    WINDOW_LAST_52W,
    compute_comparison_windows,
)
from industry_intelligence.analysis.models import (
    CLAIM_TYPE_FACT,
    CLAIM_TYPE_INFERENCE,
    AnalysisResult,
    Claim,
)
from industry_intelligence.llm.provider import LLMError
from industry_intelligence.storage import SQLiteStore


class _DummyAgent(AnalysisAgent):
    analysis_type = "market"

    def analyze(self, run_id: str) -> AnalysisResult:  # pragma: no cover
        return AnalysisResult(analysis_type=self.analysis_type, period_start="a", period_end="b")


def _agent(sample_topic, sample_task, provider=None):
    store = SQLiteStore(":memory:")
    return _DummyAgent(provider, store, "模板", sample_topic, sample_task)


def test_agent_construction(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    assert agent.analysis_type == "market"
    assert agent._topic.id == "t1"
    assert agent._task.id == "tk1"


def test_build_messages(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    messages = agent._build_messages("输入数据")
    # 单条 user：模板 + 输入数据（DeepSeek json_object 只检查 user 消息）
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "模板\n\n输入数据"


def test_build_messages_no_template(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    agent._prompt_template = ""
    messages = agent._build_messages("输入数据")
    assert messages == [{"role": "user", "content": "输入数据"}]


def test_claim_id_deterministic(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    assert agent._claim_id("同一句话", "r1") == agent._claim_id("同一句话", "r1")
    assert len(agent._claim_id("同一句话", "r1")) == 16
    assert agent._claim_id("同一句话", "r1") != agent._claim_id("另一句", "r1")


def test_make_claim_valid(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    claim = agent._make_claim(
        {
            "claim_text": "市场容量扩大",
            "claim_type": CLAIM_TYPE_FACT,
            "confidence": 0.9,
            "entity_id": "特来电",
        },
        run_id="r1",
    )
    assert isinstance(claim, Claim)
    assert claim.analysis_type == "market"
    assert claim.entity_id == "特来电"
    assert claim.topic_id == "t1"
    assert claim.run_id == "r1"


def test_make_claim_rejects_bad_type(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    claim = agent._make_claim(
        {"claim_text": "t", "claim_type": "bogus", "confidence": 0.5},
        run_id="r1",
    )
    assert claim is None


def test_make_claim_clamps_confidence(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    claim = agent._make_claim(
        {"claim_text": "t", "claim_type": CLAIM_TYPE_INFERENCE, "confidence": 3.0},
        run_id="r1",
    )
    assert claim is not None
    assert claim.confidence == 1.0


def test_make_claim_defaults_entity_to_arg(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    claim = agent._make_claim(
        {"claim_text": "t", "claim_type": CLAIM_TYPE_FACT, "confidence": 0.5},
        run_id="r1",
        entity_id="特来电",
    )
    assert claim is not None
    assert claim.entity_id == "特来电"


def test_evidence_from_requires_fallback(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    ev = agent._evidence_from("c1", [], [])
    assert ev == []
    ev2 = agent._evidence_from(
        "c1", ["d1", "d2"], [], fallback_document_ids=["d9"]
    )
    assert [e.document_id for e in ev2] == ["d1", "d2"]


def test_evidence_from_fallback_fills_empty(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task)
    ev = agent._evidence_from(
        "c1", [], [], fallback_document_ids=["d1"], fallback_observation_ids=["o1"]
    )
    assert len(ev) == 2
    assert any(e.document_id == "d1" for e in ev)
    assert any(e.observation_id == "o1" for e in ev)


def test_generate_structured_safe_records_error(sample_topic, sample_task) -> None:
    from unittest import mock

    from industry_intelligence.llm.provider import LLMProvider

    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    agent = _agent(sample_topic, sample_task, provider=provider)
    errors: list[str] = []
    result = agent._generate_structured_safe("p", {"type": "object"}, errors)
    assert result == {}
    assert errors == ["market: boom"]


def test_generate_structured_safe_none_provider(sample_topic, sample_task) -> None:
    agent = _agent(sample_topic, sample_task, provider=None)
    errors: list[str] = []
    assert agent._generate_structured_safe("p", {"type": "object"}, errors) == {}


def test_generate_structured_safe_merges_template(sample_topic, sample_task) -> None:
    from unittest import mock

    from industry_intelligence.llm.provider import LLMProvider

    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    agent = _agent(sample_topic, sample_task, provider=provider)
    errors: list[str] = []
    agent._generate_structured_safe("数据", {"type": "object"}, errors)
    sent_prompt = provider.generate_structured.call_args.args[0]
    # 模板 + 数据 合并进同一条 user 消息（DeepSeek json_object 只检查 user）
    assert sent_prompt == "模板\n\n数据"
    assert errors == []


def test_compute_windows_reference_based(sample_task) -> None:
    ref = "2026-08-11T00:00:00+00:00"
    windows = compute_comparison_windows(sample_task, reference_date=ref)
    cur_start, cur_end = windows[WINDOW_CURRENT]
    last_start, last_end = windows[WINDOW_LAST]
    assert cur_end == ref
    # current 为过去 7 天
    assert cur_start == "2026-08-04T00:00:00+00:00"
    # last 为再往前 7 天
    assert last_start == "2026-07-28T00:00:00+00:00"
    assert last_end == "2026-08-04T00:00:00+00:00"


def test_compute_windows_defaults_now(sample_task) -> None:
    windows = compute_comparison_windows(sample_task)
    cur_start, cur_end = windows[WINDOW_CURRENT]
    now = datetime.now(UTC)
    end = datetime.fromisoformat(cur_end)
    start = datetime.fromisoformat(cur_start)
    assert (now - end).total_seconds() < 60
    assert (end - start).days == 7


def test_compute_windows_sorted(sample_task) -> None:
    windows = compute_comparison_windows(sample_task, reference_date="2026-08-11T00:00:00+00:00")
    assert windows[WINDOW_LAST_52W][0] < windows[WINDOW_LAST_12W][0] < windows[WINDOW_LAST_4W][0]
