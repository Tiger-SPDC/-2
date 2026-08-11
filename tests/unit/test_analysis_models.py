"""分析数据模型单元测试。"""

from __future__ import annotations

import pytest

from industry_intelligence.analysis import (
    CLAIM_TYPE_FACT,
    CLAIM_TYPE_UNKNOWN,
    EVIDENCE_ROLE_PRIMARY,
    AnalysisResult,
    Claim,
    ClaimEvidence,
    IndexScore,
    TrendIndicator,
    make_claim_id,
)


def test_make_claim_id_deterministic() -> None:
    a = make_claim_id("特来电发布超充新品", "technology", "r1")
    b = make_claim_id("特来电发布超充新品", "technology", "r1")
    assert a == b
    assert len(a) == 16


def test_make_claim_id_differs_by_type_and_run() -> None:
    base = make_claim_id("同一句话", "market", "r1")
    assert make_claim_id("同一句话", "competitor", "r1") != base
    assert make_claim_id("同一句话", "market", "r2") != base


def test_claim_construction() -> None:
    c = Claim(
        claim_id="c1",
        claim_text="特来电本周发布超充新品",
        claim_type=CLAIM_TYPE_FACT,
        confidence=0.9,
        entity_id="特来电",
        analysis_type="technology",
        topic_id="t1",
        run_id="r1",
    )
    assert c.claim_type == "fact"
    assert c.entity_id == "特来电"


def test_claim_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="claim_type"):
        Claim(
            claim_id="c1", claim_text="t", claim_type="bogus", confidence=0.5,
            entity_id=None, analysis_type="market", topic_id="t1", run_id="r1",
        )


def test_claim_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        Claim(
            claim_id="c1", claim_text="t", claim_type=CLAIM_TYPE_FACT,
            confidence=1.5, entity_id=None, analysis_type="market",
            topic_id="t1", run_id="r1",
        )


def test_claim_evidence_document() -> None:
    ev = ClaimEvidence(claim_id="c1", document_id="d1")
    assert ev.evidence_role == EVIDENCE_ROLE_PRIMARY


def test_claim_evidence_requires_source() -> None:
    with pytest.raises(ValueError, match="document_id or observation_id"):
        ClaimEvidence(claim_id="c1")


def test_claim_evidence_invalid_role() -> None:
    with pytest.raises(ValueError, match="evidence_role"):
        ClaimEvidence(claim_id="c1", document_id="d1", evidence_role="bogus")


def test_index_score_defaults() -> None:
    idx = IndexScore(
        index_name="competitive_activity_index", entity_id="特来电",
        score=60.0, period_start="2026-08-01", period_end="2026-08-08",
    )
    assert idx.components == {}


def test_trend_indicator_computable() -> None:
    t = TrendIndicator(
        indicator_name="event_velocity", current_value=10.0, previous_value=5.0,
        delta=5.0, delta_pct=100.0, window_weeks=4,
    )
    assert t.window_weeks == 4


def test_analysis_result_defaults() -> None:
    result = AnalysisResult(analysis_type="market", period_start="a", period_end="b")
    assert result.claims == []
    assert result.indices == []
    assert result.errors == []


def test_unknown_claim_type_is_valid() -> None:
    c = Claim(
        claim_id="c1", claim_text="数据不足", claim_type=CLAIM_TYPE_UNKNOWN,
        confidence=0.3, entity_id=None, analysis_type="risk", topic_id="t1",
        run_id="r1",
    )
    assert c.claim_type == "unknown"
