"""ReviewAgent 单元测试：7 项检查编排、持久化、降级路径（全部离线）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis.review import (
    REVIEW_DOWNGRADE,
    REVIEW_PASS,
    REVIEW_REJECT,
    ReviewAgent,
    ReviewResult,
    make_review_id,
)
from industry_intelligence.config.models import ReviewConfig
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")


def _seed_store(make_doc) -> SQLiteStore:
    """写入 run + 文档 + 3 条 claim（各带 1 条文档证据）。"""
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    for i in range(1, 4):
        store.insert_document(
            make_doc(document_id=f"d{i}", title=f"文档 {i}", fetched_at=T1)
        )
        store.insert_claim(
            claim_id=f"c{i}",
            claim_text=f"结论 {i}",
            claim_type="fact",
            confidence=0.9,
            analysis_type="market",
            topic_id="t1",
            run_id="r1",
            entity_id="特来电",
        )
        store.insert_claim_evidence(
            f"c{i}", document_id=f"d{i}", evidence_role="primary_source"
        )
    return store


def _provider(payload: dict[str, object]) -> mock.Mock:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = payload
    return provider


def _agent(store, provider=None, config=None):
    return ReviewAgent(
        provider=provider,
        sqlite_store=store,
        prompt_template="review template",
        topic=mock.Mock(id="t1"),
        task=mock.Mock(id="tk1"),
        review_config=config,
    )


def test_make_review_id_is_deterministic() -> None:
    a = make_review_id("c1", "pass", "r1")
    b = make_review_id("c1", "pass", "r1")
    c = make_review_id("c1", "reject", "r1")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_no_provider_returns_empty(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    agent = ReviewAgent(
        provider=None,
        sqlite_store=store,
        prompt_template="tpl",
        topic=sample_topic,
        task=sample_task,
    )
    result = agent.review("r1")
    assert isinstance(result, ReviewResult)
    assert result.reviews == []
    assert result.passed == result.rejected == result.downgraded == 0
    assert result.errors == []
    assert store.query_claim_reviews("r1") == []


def test_disabled_config_returns_empty(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    agent = ReviewAgent(
        provider=_provider({"reviews": []}),
        sqlite_store=store,
        prompt_template="tpl",
        topic=sample_topic,
        task=sample_task,
        review_config=ReviewConfig(enabled=False),
    )
    result = agent.review("r1")
    assert result.reviews == []
    assert result.errors == []


def test_persists_mixed_verdicts(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    payload: dict[str, object] = {
        "reviews": [
            {"claim_id": "c1", "verdict": REVIEW_PASS, "reason": "ok"},
            {
                "claim_id": "c2", "verdict": REVIEW_DOWNGRADE,
                "downgrade_to": "inference", "issues": ["数字不可追溯"],
            },
            {"claim_id": "c3", "verdict": REVIEW_REJECT, "reason": "日期不符"},
        ]
    }
    result = _agent(store, _provider(payload)).review("r1")

    assert result.passed == 1
    assert result.downgraded == 1
    assert result.rejected == 1
    rows = store.query_claim_reviews("r1")
    assert len(rows) == 3
    by_claim = {row["claim_id"]: row for row in rows}
    assert by_claim["c1"]["verdict"] == "pass"
    assert by_claim["c2"]["verdict"] == "downgrade"
    assert by_claim["c2"]["downgrade_to"] == "inference"
    assert by_claim["c2"]["issues"] == '["数字不可追溯"]'
    assert by_claim["c3"]["verdict"] == "reject"


def test_skips_unknown_claim_and_duplicates(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    payload: dict[str, object] = {
        "reviews": [
            {"claim_id": "c1", "verdict": REVIEW_PASS},
            {"claim_id": "c1", "verdict": REVIEW_REJECT},  # 重复 → 跳过
            {"claim_id": "nope", "verdict": REVIEW_PASS},  # 未知 → 跳过
        ]
    }
    result = _agent(store, _provider(payload)).review("r1")
    assert result.passed == 1
    assert result.rejected == 0
    # 只有第一条 c1(pass) 被持久化；重复与未知 claim 被跳过
    rows = store.query_claim_reviews("r1")
    assert len(rows) == 1
    assert rows[0]["claim_id"] == "c1"
    assert rows[0]["verdict"] == "pass"


def test_invalid_verdict_recorded_error(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    payload: dict[str, object] = {
        "reviews": [{"claim_id": "c1", "verdict": "maybe"}]
    }
    result = _agent(store, _provider(payload)).review("r1")
    assert result.passed == 0
    assert any("invalid verdict" in e for e in result.errors)
    assert store.query_claim_reviews("r1") == []


def test_downgrade_requires_downgrade_to(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    payload: dict[str, object] = {
        "reviews": [{"claim_id": "c1", "verdict": REVIEW_DOWNGRADE}]
    }
    result = _agent(store, _provider(payload)).review("r1")
    assert result.downgraded == 0
    assert any("downgrade requires" in e for e in result.errors)


def test_llm_error_degrades_gracefully(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("review boom")
    result = _agent(store, provider).review("r1")
    assert result.reviews == []
    assert any("review boom" in e for e in result.errors)
    assert store.query_claim_reviews("r1") == []


def test_missing_reviews_array_recorded_error(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    # LLM 返回了内容但没有 reviews 数组 → 记录错误
    result = _agent(store, _provider({"unexpected": "payload"})).review("r1")
    assert any("reviews 数组" in e for e in result.errors)
    assert store.query_claim_reviews("r1") == []


def test_generate_structured_merges_template(make_doc, sample_topic, sample_task) -> None:
    """review.md 模板必须合并进 user 消息（DeepSeek json_object 只检查 user）。"""
    store = _seed_store(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"reviews": []}
    agent = _agent(store, provider)
    errors: list[str] = []
    agent._generate_structured_safe("数据", errors)
    sent_prompt = provider.generate_structured.call_args.args[0]
    assert sent_prompt.startswith(agent._prompt_template)
    assert "数据" in sent_prompt
