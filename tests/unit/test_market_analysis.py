"""Market Analyst 单元测试：MMI 公式 + mock LLM 市场分析。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.analysis.market import (
    MARKET_SCHEMA,
    MarketAnalyst,
    compute_mmi,
)
from industry_intelligence.analysis.models import INDEX_MMI
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.metrics.models import Observation
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
T_LAST = (NOW - timedelta(days=10)).isoformat(timespec="seconds")


def _store_with_observations(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(document_id="d1", title="市场规模报告", fetched_at=T1)
    )
    store.insert_observation(
        Observation(
            observation_id="o1", document_id="d1", metric_id="market_sales",
            entity_id="特来电", value=110.0, unit="万台", period_start=T_LAST,
            period_end=T1, region=None, confidence=0.9, evidence_text="e",
        )
    )
    return store


def _analyst(store, provider=None, topic=None, task=None):
    return MarketAnalyst(provider, store, "模板", topic, task)


def test_compute_mmi_growth() -> None:
    idx = compute_mmi(
        [{"metric_id": "market_sales", "value": 110.0}],
        [{"metric_id": "market_sales", "value": 100.0}],
        "a", "b",
    )
    assert idx.index_name == INDEX_MMI
    # 3.0 × 10% × 100 = 30
    assert idx.score == 30.0
    assert idx.components == {"market_sales": 0.3}


def test_compute_mmi_no_previous_data() -> None:
    idx = compute_mmi(
        [{"metric_id": "market_sales", "value": 110.0}],
        [],
        "a", "b",
    )
    assert idx.score == 0.0


def test_compute_mmi_decline_clamps_to_zero() -> None:
    idx = compute_mmi(
        [{"metric_id": "market_sales", "value": 90.0}],
        [{"metric_id": "market_sales", "value": 100.0}],
        "a", "b",
    )
    assert idx.score == 0.0
    assert idx.components["market_sales"] == -0.3


def test_compute_mmi_metric_weights() -> None:
    idx = compute_mmi(
        [{"metric_id": "market_share", "value": 55.0}],
        [{"metric_id": "market_share", "value": 50.0}],
        "a", "b",
    )
    # 2.5 × 10% × 100 = 25
    assert idx.score == 25.0


def test_compute_mmi_averages_observations() -> None:
    idx = compute_mmi(
        [{"metric_id": "price", "value": 11.0}, {"metric_id": "price", "value": 9.0}],
        [{"metric_id": "price", "value": 10.0}],
        "a", "b",
    )
    # avg current 10 vs prev 10 → 0
    assert idx.score == 0.0


def test_analyze_with_mock_provider(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_observations(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {
        "claims": [
            {
                "claim_text": "市场销量环比增长约 10%（重算）",
                "claim_type": "fact",
                "confidence": 0.8,
                "entity_id": "特来电",
                "evidence_document_ids": ["d1"],
                "evidence_observation_ids": ["o1"],
            }
        ]
    }
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.analysis_type == "market"
    assert len(result.claims) == 1
    assert len(result.indices) == 1
    assert result.indices[0].index_name == INDEX_MMI
    # 证据被保留（d1、o1 均在窗口内真实存在）
    assert result.evidences[0].document_id == "d1"
    assert any(e.observation_id == "o1" for e in result.evidences)


def test_analyze_no_provider_still_mmi(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_observations(make_doc)
    analyst = _analyst(store, provider=None, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.indices[0].index_name == INDEX_MMI


def test_analyze_llm_error(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_observations(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMError("boom")
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    result = analyst.analyze("r1")
    assert result.claims == []
    assert result.errors
    assert len(result.indices) == 1


def test_analyze_sends_schema(make_doc, sample_topic, sample_task) -> None:
    store = _store_with_observations(make_doc)
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"claims": []}
    analyst = _analyst(store, provider=provider, topic=sample_topic, task=sample_task)
    analyst.analyze("r1")
    assert provider.generate_structured.call_args.args[1] == MARKET_SCHEMA
