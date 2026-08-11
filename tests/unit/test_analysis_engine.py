"""AnalysisEngine 单元测试：编排、失败隔离、持久化与证据覆盖率。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis import engine as engine_mod
from industry_intelligence.analysis.engine import AnalysisEngine, EngineResult
from industry_intelligence.analysis.models import (
    ANALYSIS_MARKET,
    TREND_INDICATORS,
)
from industry_intelligence.config.models import AnalysisConfig
from industry_intelligence.intelligence.models import Event
from industry_intelligence.llm.provider import LLMProvider
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")


def _event(event_id: str, etype: str, entity: str = "特来电") -> Event:
    return Event(
        event_id=event_id,
        event_type_id=etype,
        title=f"{event_id}{etype}",
        event_date=T1,
        summary="摘要",
        document_ids=["d1"],
        entity_ids=[entity],
        confidence=1.0,
        topic_id="t1",
    )


def _claims_payload() -> dict[str, object]:
    return {
        "claims": [
            {
                "claim_text": "竞争活动活跃，招标订单密集",
                "claim_type": "fact",
                "confidence": 0.9,
                "entity_id": "特来电",
                "evidence_document_ids": ["d1"],
                "evidence_observation_ids": [],
            }
        ]
    }


def _store(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(
            document_id="d1", title="测试文档", fetched_at=T1,
            matched_entities=["特来电"],
        )
    )
    store.insert_event(_event("e1", "bid_order"))
    return store


def _provider() -> mock.Mock:
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = _claims_payload()
    return provider


def _engine(store, provider=None, topic=None, task=None, config=None):
    return AnalysisEngine(
        provider=provider,
        sqlite_store=store,
        topic=topic,
        task=task,
        prompts={},
        analysis_config=config,
    )


def test_run_orchestrates_all_dimensions(make_doc, sample_topic, sample_task) -> None:
    store = _store(make_doc)
    result = _engine(store, _provider(), sample_topic, sample_task).run("r1")
    assert isinstance(result, EngineResult)
    assert len(result.results) == 4
    assert {r.analysis_type for r in result.results} == {
        "competitor", "market", "technology", "risk",
    }
    # 每个维度都有确定性指数（competitor 按实体输出多条 CAI）
    for r in result.results:
        assert len(r.indices) >= 1
        assert all(i.score >= 0.0 for i in r.indices)
    assert result.errors == []


def test_run_persists_claims_and_coverage(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store(make_doc)
    result = _engine(store, _provider(), sample_topic, sample_task).run("r1")
    # 4 维度 × 1 claim = 4 条，全部有证据 → 覆盖率 100%
    assert result.analysis_claims == 4
    assert result.evidence_coverage == 1.0
    rows = store.query_claims("r1")
    assert len(rows) == 4
    for row in rows:
        assert store.query_claim_evidence(row["claim_id"])
        assert row["run_id"] == "r1"
        assert row["topic_id"] == "t1"


def test_trends_computed(make_doc, sample_topic, sample_task) -> None:
    store = _store(make_doc)
    result = _engine(store, _provider(), sample_topic, sample_task).run("r1")
    assert set(result.trends.keys()) == TREND_INDICATORS


def test_single_analyst_failure_does_not_abort(
    make_doc, sample_topic, sample_task
) -> None:
    class BoomAnalyst:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ARG002
            pass

        def analyze(self, run_id: str):  # noqa: ARG002
            raise RuntimeError("boom")

    original = engine_mod._ANALYST_FACTORIES
    try:
        engine_mod._ANALYST_FACTORIES = {
            **original,
            "competitor": BoomAnalyst,  # type: ignore[dict-item]
        }
        store = _store(make_doc)
        result = _engine(store, _provider(), sample_topic, sample_task).run("r1")
    finally:
        engine_mod._ANALYST_FACTORIES = original

    assert len(result.results) == 3  # competitor 失败，其余照常
    assert any("competitor" in e and "boom" in e for e in result.errors)
    assert result.analysis_claims == 3


def test_unknown_dimension_recorded(make_doc, sample_topic, sample_task) -> None:
    config = AnalysisConfig(enabled_dimensions=["competitor", "bogus"])
    store = _store(make_doc)
    result = _engine(store, _provider(), sample_topic, sample_task, config).run("r1")
    assert len(result.results) == 1
    assert result.results[0].analysis_type == "competitor"
    assert any("bogus" in e for e in result.errors)


def test_disabled_dimensions_only_run_selected(
    make_doc, sample_topic, sample_task
) -> None:
    config = AnalysisConfig(enabled_dimensions=[ANALYSIS_MARKET])
    store = _store(make_doc)
    result = _engine(store, _provider(), sample_topic, sample_task, config).run("r1")
    assert len(result.results) == 1
    assert result.results[0].analysis_type == ANALYSIS_MARKET
    assert result.analysis_claims == 1


def test_no_provider_still_indices_no_claims(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store(make_doc)
    result = _engine(store, provider=None, topic=sample_topic, task=sample_task).run(
        "r1"
    )
    assert len(result.results) == 4
    for r in result.results:
        assert r.claims == []
        assert len(r.indices) >= 1
    assert result.analysis_claims == 0
    assert result.evidence_coverage == 0.0


def test_empty_run_coverage_zero(make_doc, sample_topic, sample_task) -> None:
    # 无 run 记录 → 无 claim → 覆盖率 0
    store = SQLiteStore(":memory:")
    result = _engine(store, _provider(), sample_topic, sample_task).run("r0")
    assert result.analysis_claims == 0
    assert result.evidence_coverage == 0.0
