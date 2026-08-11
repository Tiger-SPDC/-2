"""Technology Analyst 单元测试：THI 公式 + mock LLM 技术分析。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis.models import INDEX_THI
from industry_intelligence.analysis.technology import (
    TECHNOLOGY_SCHEMA,
    TechnologyAnalyst,
    compute_thi,
)
from industry_intelligence.config.models import TopicKeywords
from industry_intelligence.intelligence.models import Event
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")


def _tech_topic(sample_topic):
    return replace(
        sample_topic,
        keywords=TopicKeywords(
            core=sample_topic.keywords.core,
            technology=["超充", "液冷"],
            events=sample_topic.keywords.events,
        ),
    )


def _event(event_id, etype, entity="特来电"):
    return Event(
        event_id=event_id,
        event_type_id=etype,
        title=f"{entity}{etype}",
        event_date=T1,
        summary="摘要",
        document_ids=["d1"],
        entity_ids=[entity],
        confidence=1.0,
        topic_id="t1",
    )


def _store_with_tech(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1", title="特来电发布液冷超充新品", fetched_at=T1,
            matched_keywords=["超充", "液冷"], matched_entities=["特来电"],
        )
    )
    store.insert_event(_event("e1", "new_product"))
    store.insert_event(_event("e2", "technology_rd"))
    return store


def _analyst(store, provider=None, topic=None, task=None):
    return TechnologyAnalyst(provider, store, "模板", topic, task)


def test_compute_thi_weights() -> None:
    idx = compute_thi(
        [_event("e1", "new_product")], keyword_doc_count=0,
        period_start="a", period_end="b",
    )
    assert idx.index_name == INDEX_THI
    # 2.0 × 10 = 20
    assert idx.score == 20.0
    assert idx.components["new_product"] == 2.0


def test_compute_thi_keyword_docs_add_weight() -> None:
    idx = compute_thi(
        [_event("e1", "new_product")], keyword_doc_count=1,
        period_start="a", period_end="b",
    )
    # (2.0 + 0.5) × 10 = 25
    assert idx.score == 25.0
    assert idx.components["technology_keyword_docs"] == 1.0


def test_compute_thi_empty() -> None:
    idx = compute_thi([], keyword_doc_count=0, period_start="a", period_end="b")
    assert idx.score == 0.0


def test_analyze_with_mock_provider(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_tech(make_doc)
    topic = _tech_topic(sample_topic)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "claims": [
            {
                "claim_text": "特来电推出液冷超充新品，充电功率显著提升",
                "claim_type": "fact",
                "confidence": 0.85,
                "entity_id": "特来电",
                "evidence_document_ids": ["d1"],
                "evidence_observation_ids": [],
            }
        ]
    }
    analyst = _analyst(store, provider=provider, topic=topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.analysis_type == "technology"
    assert len(result.claims) == 1
    assert result.indices[0].index_name == INDEX_THI
    # new_product 2.0 + technology_rd 1.5 + 关键词文档 0.5 → 4.0 × 10 = 40
    assert result.indices[0].score == 40.0
    assert result.evidences[0].document_id == "d1"


def test_analyze_no_tech_events(make_doc, sample_topic, sample_task) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(document_id="d1", title="普通新闻", fetched_at=T1)
    )
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.indices[0].score == 0.0
    assert result.claims == []


def test_analyze_llm_error(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_tech(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    analyst = _analyst(store, provider=provider, topic=_tech_topic(sample_topic), task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.errors
    assert len(result.indices) == 1


def test_analyze_sends_schema(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_tech(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    analyst = _analyst(store, provider=provider, topic=_tech_topic(sample_topic), task=sample_task)
    analyst.analyze("r1")
    assert provider.generate_structured.call_args.args[1] == TECHNOLOGY_SCHEMA
