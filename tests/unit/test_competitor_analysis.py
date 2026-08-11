"""Competitor Analyst 单元测试：CAI 公式 + mock LLM 分析。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis.competitor import (
    COMPETITOR_SCHEMA,
    CompetitorAnalyst,
    compute_cai,
)
from industry_intelligence.analysis.models import CLAIM_TYPE_FACT, INDEX_CAI
from industry_intelligence.intelligence.models import Event
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
T_LAST = (NOW - timedelta(days=10)).isoformat(timespec="seconds")


def _event(event_id, etype, entity, date, document_id="d1"):
    return Event(
        event_id=event_id,
        event_type_id=etype,
        title=f"{entity}事件",
        event_date=date,
        summary="摘要",
        document_ids=[document_id],
        entity_ids=[entity],
        confidence=1.0,
        topic_id="t1",
    )


def _analyst(store, provider=None, topic=None, task=None):
    return CompetitorAnalyst(
        provider=provider,
        sqlite_store=store,
        prompt_template="模板",
        topic=topic,
        task=task,
    )


def _store_with_data(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1",
            title="特来电发布超充新品",
            fetched_at=T1,
            matched_entities=["特来电"],
        )
    )
    store.insert_event(_event("e1", "new_product", "特来电", T1))
    store.insert_event(_event("e2", "financing", "特来电", T1))
    return store


def test_compute_cai_weights(make_doc) -> None:
    events = [
        _event("e1", "bid_order", "特来电", T1),
        _event("e2", "new_product", "特来电", T1),
    ]
    idx = compute_cai(events, "特来电", "a", "b")
    assert idx.index_name == INDEX_CAI
    assert idx.score == 50.0  # (3 + 2) × 10
    assert idx.components == {"bid_order": 3.0, "new_product": 2.0}


def test_compute_cai_empty(make_doc) -> None:
    idx = compute_cai([], "特来电", "a", "b")
    assert idx.score == 0.0
    assert idx.components == {}


def test_compute_cai_unknown_type_low_weight(make_doc) -> None:
    events = [_event("e1", "other", "特来电", T1)]
    idx = compute_cai(events, "特来电", "a", "b")
    assert idx.score == 5.0  # 0.5 × 10


def test_compute_cai_caps_at_100(make_doc) -> None:
    events = [
        _event(f"e{i}", "bid_order", "特来电", T1) for i in range(6)
    ]
    idx = compute_cai(events, "特来电", "a", "b")
    assert idx.score == 100.0


def test_analyze_with_mock_provider(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_data(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "claims": [
            {
                "claim_text": "特来电本周发布超充新品，加快高端布局",
                "claim_type": "fact",
                "confidence": 0.9,
                "entity_id": "特来电",
                "evidence_document_ids": ["d1"],
                "evidence_observation_ids": [],
            },
            {
                "claim_text": "特来电下季度或将加速海外扩张",
                "claim_type": "forecast",
                "confidence": 0.6,
                "entity_id": "特来电",
                "evidence_document_ids": [],
                "evidence_observation_ids": [],
            },
        ]
    }
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.analysis_type == "competitor"
    assert len(result.claims) == 2
    assert result.claims[0].claim_type == CLAIM_TYPE_FACT
    # 每条 Claim 至少一条证据
    assert len(result.evidences) == 2
    assert {e.claim_id for e in result.evidences} == {c.claim_id for c in result.claims}
    # 第二条无显式证据 → 兜底到实体文档 d1
    second = next(e for e in result.evidences if e.claim_id == result.claims[1].claim_id)
    assert second.document_id == "d1"
    # CAI 指数存在
    assert len(result.indices) == 2
    assert {i.entity_id for i in result.indices} == {"特来电", "星星充电"}


def test_analyze_filters_hallucinated_evidence(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store_with_data(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "claims": [
            {
                "claim_text": "特来电发布新品",
                "claim_type": "fact",
                "confidence": 0.8,
                "entity_id": "特来电",
                "evidence_document_ids": ["no_such_doc"],
                "evidence_observation_ids": [],
            }
        ]
    }
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert len(result.claims) == 1
    ev = result.evidences[0]
    assert ev.document_id == "d1"  # 幻觉 ID 被过滤，兜底到真实文档


def test_analyze_no_entities(make_doc, sample_topic, sample_task) -> None:
    from industry_intelligence.config.models import TopicProfile

    empty_topic = TopicProfile(
        id="t1", name="空", version="1.0",
        scope=sample_topic.scope,
        entities=sample_topic.entities.__class__(companies=[]),
        keywords=sample_topic.keywords, metrics=[],
    )
    store = _store_with_data(make_doc)
    analyst = _analyst(store, provider=None, topic=empty_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.indices == []


def test_analyze_llm_error_still_computes_indices(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store_with_data(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.errors
    # 确定性 CAI 不受 LLM 失败影响
    assert len(result.indices) == 2


def test_analyze_sends_schema(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_data(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    analyst.analyze("r1")
    assert provider.generate_structured.call_args.args[1] == COMPETITOR_SCHEMA
