"""ReportDataBuilder 单元测试：SQLite → 格式无关 bundle（全离线）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics.models import Observation
from industry_intelligence.reporting.builder import ReportDataBuilder
from industry_intelligence.reporting.engine import FORMAT_MARKDOWN, ReportEngine
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
TODAY = NOW.isoformat(timespec="seconds")


def _seed_store(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1", title="文档一", fetched_at=TODAY,
            matched_entities=["特来电"],
        )
    )
    store.insert_event(
        Event(
            event_id="e1", event_type_id="new_product", title="发布新品",
            event_date=TODAY, summary="摘要", document_ids=["d1"],
            entity_ids=["特来电"], confidence=0.9, topic_id="t1",
        )
    )
    store.insert_observation(
        Observation(
            observation_id="o1", document_id="d1", metric_id="station_count",
            entity_id="特来电", value=100.0, unit="座",
            period_start=T1, period_end=TODAY, region="中国",
            confidence=0.9, evidence_text="证据文本",
        )
    )
    store.insert_claim(
        claim_id="c1", claim_text="特来电市占率上升", claim_type="fact",
        confidence=0.9, analysis_type="market", topic_id="t1",
        run_id="r1", entity_id="特来电",
    )
    store.insert_claim_evidence("c1", document_id="d1", evidence_role="primary_source")
    store.insert_claim_review("rv1", "c1", "pass", "r1", reason="ok")
    return store


def _builder(store, sample_topic, sample_task) -> ReportDataBuilder:
    return ReportDataBuilder(store, sample_topic, sample_task)


def test_build_populated_bundle(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    bundle = _builder(store, sample_topic, sample_task).build("r1")

    assert bundle.run_id == "r1"
    assert bundle.topic_id == "t1"
    assert bundle.task_id == "tk1"
    assert len(bundle.documents) == 1
    assert len(bundle.events) == 1
    assert len(bundle.observations) == 1
    assert len(bundle.companies) == 2  # sample_topic 内 2 家实体
    assert len(bundle.claims) == 1
    assert bundle.claims[0]["evidence"]  # 证据已合并
    assert len(bundle.review_results) == 1
    assert bundle.review_results[0]["verdict"] == "pass"


def test_build_quality_metrics(make_doc, sample_topic, sample_task) -> None:
    store = _seed_store(make_doc)
    bundle = _builder(store, sample_topic, sample_task).build(
        "r1", analysis_claims=1, evidence_coverage=1.0
    )
    q = bundle.quality
    assert q["document_count"] == 1.0
    assert q["event_count"] == 1.0
    assert q["observation_count"] == 1.0
    assert q["claim_count"] == 1.0
    assert q["evidence_coverage"] == 1.0
    assert q["claims_with_evidence_rate"] == 1.0
    assert q["review_count"] == 1.0
    assert q["review_reject_count"] == 0.0
    assert q["review_reject_rate"] == 0.0
    assert q["company_count"] == 2.0


def test_build_empty_run(make_doc, sample_topic, sample_task) -> None:
    store = SQLiteStore(":memory:")
    bundle = _builder(store, sample_topic, sample_task).build("r0")
    assert bundle.status == "unknown"
    assert bundle.events == []
    assert bundle.claims == []
    assert bundle.review_results == []
    assert bundle.quality["claim_count"] == 0.0
    assert bundle.quality["evidence_coverage"] == 0.0
    assert bundle.errors == []


def test_build_forwards_indices_and_trends(
    make_doc, sample_topic, sample_task
) -> None:
    store = _seed_store(make_doc)
    indices = [mock.Mock(index_name="CAI", entity_id="特来电", score=0.8)]
    trends = {
        "event_velocity": [mock.Mock(current_value=2.0, previous_value=1.0)]
    }
    bundle = _builder(store, sample_topic, sample_task).build(
        "r1", indices=indices, trends=trends
    )
    assert bundle.indices[0]["index_name"] == "CAI"
    assert bundle.trends["event_velocity"][0]["current_value"] == 2.0


def test_build_forwards_hot_topics(make_doc, sample_topic, sample_task) -> None:
    """build() 透传 LLM 动态热点到 bundle，供摘要/报告展示。"""
    store = _seed_store(make_doc)
    bundle = _builder(store, sample_topic, sample_task).build(
        "r1", hot_topics=["液冷超充", "V2G"]
    )
    assert bundle.hot_topics == ["液冷超充", "V2G"]
    # 缺省为空列表，不抛错
    empty = _builder(store, sample_topic, sample_task).build("r1")
    assert empty.hot_topics == []


def test_engine_build_shared_bundle(
    make_doc, sample_topic, sample_task, tmp_path
) -> None:
    # ReportEngine 与 ReportDataBuilder 使用同一 bundle 管线
    store = _seed_store(make_doc)
    engine = ReportEngine(
        store, sample_topic, sample_task, output_dir=tmp_path / "reports"
    )
    result = engine.run("r1", analysis_claims=1, evidence_coverage=1.0)
    assert result.paths.get(FORMAT_MARKDOWN)


def test_canonicalize_entity(make_doc, sample_topic, sample_task) -> None:
    """entity_id 归一化：别名 → canonical；非跟踪企业/None/空串不变。"""
    b = _builder(SQLiteStore(":memory:"), sample_topic, sample_task)
    assert b._canonicalize_entity("特来电新能源") == "特来电"  # alias → canonical
    assert b._canonicalize_entity("特来电") == "特来电"  # canonical 不变
    assert b._canonicalize_entity("蔚来") == "蔚来"  # 非跟踪企业信任原值
    assert b._canonicalize_entity(None) is None
    assert b._canonicalize_entity("") == ""


def test_build_canonicalizes_entity_alias(
    make_doc, sample_topic, sample_task
) -> None:
    """claim 的 entity_id 为跟踪企业别名时，bundle 中归一到 canonical_name。"""
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1", title="文档一", fetched_at=TODAY,
            matched_entities=["特来电"],
        )
    )
    store.insert_claim(
        claim_id="c1", claim_text="特来电新能源市占率上升", claim_type="fact",
        confidence=0.9, analysis_type="market", topic_id="t1",
        run_id="r1", entity_id="特来电新能源",
    )
    store.insert_claim_evidence("c1", document_id="d1", evidence_role="primary_source")
    bundle = _builder(store, sample_topic, sample_task).build("r1")
    assert bundle.claims[0]["entity_id"] == "特来电"
