"""Risk Signal Analyst 单元测试：RSI 公式 + mock LLM 风险分析。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis.models import INDEX_RSI
from industry_intelligence.analysis.risk import (
    RISK_SCHEMA,
    RiskAnalyst,
    compute_rsi,
)
from industry_intelligence.intelligence.models import Event
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")


def _event(event_id, etype, entity="特来电"):
    return Event(
        event_id=event_id,
        event_type_id=etype,
        title=f"{entity}{etype}事件",
        event_date=T1,
        summary="摘要",
        document_ids=["d1"],
        entity_ids=[entity],
        confidence=1.0,
        topic_id="t1",
    )


def _store_with_risk(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1", title="充电桩安全事故通报", fetched_at=T1,
            matched_entities=["特来电"],
        )
    )
    store.insert_event(_event("e1", "recall_accident"))
    store.insert_event(_event("e2", "litigation_compliance"))
    return store


def _analyst(store, provider=None, topic=None, task=None):
    return RiskAnalyst(provider, store, "模板", topic, task)


def test_compute_rsi_severity_weights() -> None:
    idx = compute_rsi(
        [_event("e1", "recall_accident"), _event("e2", "litigation_compliance")],
        "a", "b",
    )
    assert idx.index_name == INDEX_RSI
    # (4 + 3) × 10
    assert idx.score == 70.0
    assert idx.components == {"recall_accident": 4.0, "litigation_compliance": 3.0}


def test_compute_rsi_empty() -> None:
    idx = compute_rsi([], "a", "b")
    assert idx.score == 0.0


def test_compute_rsi_unknown_type_default() -> None:
    idx = compute_rsi([_event("e1", "other_risk")], "a", "b")
    # 未知风险类型权重 1.0 × 10
    assert idx.score == 10.0


def test_analyze_with_mock_provider(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_risk(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "claims": [
            {
                "claim_text": "特来电因产品安全事件被通报，存在较高合规风险",
                "claim_type": "inference",
                "confidence": 0.75,
                "entity_id": "特来电",
                "severity": "high",
                "evidence_document_ids": ["d1"],
                "evidence_observation_ids": [],
            }
        ]
    }
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.analysis_type == "risk"
    assert len(result.claims) == 1
    assert result.indices[0].index_name == INDEX_RSI
    assert result.evidences[0].document_id == "d1"
    assert result.indices[0].score == 70.0  # (4 + 3) × 10


def test_analyze_no_risk_events(make_doc, sample_topic, sample_task) -> None:
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
    store = _store_with_risk(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.errors
    assert len(result.indices) == 1


def test_analyze_sends_schema_with_severity(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store_with_risk(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    analyst.analyze("r1")
    schema = provider.generate_structured.call_args.args[1]
    assert schema == RISK_SCHEMA
    sev = schema["properties"]["claims"]["items"]["properties"]["severity"]
    assert set(sev["enum"]) == {"high", "medium", "low"}
