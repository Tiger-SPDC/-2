"""SQLite Phase 3 扩展测试：claims / 历史窗口查询 / 聚合（全部 :memory:）。"""

from __future__ import annotations

import sqlite3

import pytest

from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics.models import Observation
from industry_intelligence.storage import SQLiteStore

T0 = "2026-08-01T00:00:00+00:00"
T1 = "2026-08-02T00:00:00+00:00"
T2 = "2026-08-10T00:00:00+00:00"


def _insert_doc(store: SQLiteStore, make_doc, document_id: str, entities=None) -> None:
    store.insert_document(
        make_doc(
            document_id=document_id,
            title=f"标题{document_id}",
            fetched_at=T0,
            matched_entities=entities or [],
        )
    )


def _insert_event(
    store: SQLiteStore, event_id: str, event_type_id: str, date: str, entities
) -> None:
    store.insert_event(
        Event(
            event_id=event_id,
            event_type_id=event_type_id,
            title=f"事件{event_id}",
            event_date=date,
            summary="摘要",
            document_ids=[],
            entity_ids=entities,
            confidence=0.9,
            topic_id="t1",
        )
    )


def test_phase3_tables_created(make_doc) -> None:
    store = SQLiteStore(":memory:")
    names = {
        row["name"] for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"claims", "claim_evidence"} <= names


def test_insert_claim_and_query(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T0)
    store.insert_claim(
        claim_id="c1",
        claim_text="特来电本周发布超充新品",
        claim_type="fact",
        confidence=0.9,
        entity_id="特来电",
        analysis_type="technology",
        topic_id="t1",
        run_id="r1",
    )
    rows = store.query_claims("r1")
    assert len(rows) == 1
    assert rows[0]["claim_type"] == "fact"
    assert rows[0]["entity_id"] == "特来电"
    assert rows[0]["analysis_type"] == "technology"


def test_insert_claim_evidence_document(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T0)
    _insert_doc(store, make_doc, "d1")
    store.insert_claim(
        claim_id="c1", claim_text="t", claim_type="inference",
        confidence=0.6, analysis_type="market", topic_id="t1", run_id="r1",
    )
    store.insert_claim_evidence("c1", document_id="d1", evidence_role="primary_source")
    ev = store.query_claim_evidence("c1")
    assert len(ev) == 1
    assert ev[0]["document_id"] == "d1"
    assert ev[0]["observation_id"] is None


def test_insert_claim_evidence_requires_source(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T0)
    store.insert_claim(
        claim_id="c1", claim_text="t", claim_type="unknown",
        confidence=0.3, analysis_type="risk", topic_id="t1", run_id="r1",
    )
    with pytest.raises(ValueError, match="document_id or observation_id"):
        store.insert_claim_evidence("c1")


def test_claim_evidence_fk_enforced(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T0)
    _insert_doc(store, make_doc, "d1")
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_claim_evidence("no_such_claim", document_id="d1")


def test_query_events_in_range(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电"])
    _insert_event(store, "e2", "financing", T2, ["特来电"])
    rows = store.query_events_in_range("t1", T0, T1)
    assert [r["event_id"] for r in rows] == ["e1"]


def test_query_events_in_range_by_type(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电"])
    _insert_event(store, "e2", "financing", T1, ["特来电"])
    rows = store.query_events_in_range("t1", T0, T2, event_type_id="financing")
    assert [r["event_id"] for r in rows] == ["e2"]


def test_query_events_by_entity(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电"])
    _insert_event(store, "e2", "new_product", T2, ["星星充电"])
    rows = store.query_events_by_entity("t1", "特来电")
    assert [r["event_id"] for r in rows] == ["e1"]


def test_query_events_by_entity_in_range(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电"])
    _insert_event(store, "e2", "financing", T2, ["特来电"])
    rows = store.query_events_by_entity("t1", "特来电", start_date=T0, end_date=T1)
    assert [r["event_id"] for r in rows] == ["e1"]


def test_query_observations_in_range_uses_period_end(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_doc(store, make_doc, "d1")
    for oid, date in (("o1", T1), ("o2", T2)):
        store.insert_observation(
            Observation(
                observation_id=oid,
                document_id="d1",
                metric_id="station_count",
                entity_id="特来电",
                value=100.0,
                unit="座",
                period_start=T0,
                period_end=date,
                region=None,
                confidence=0.9,
                evidence_text="e",
            )
        )
    rows = store.query_observations_in_range("t1", start_date=T0, end_date=T1)
    assert [r["observation_id"] for r in rows] == ["o1"]


def test_query_observations_in_range_filters_metric_entity(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_doc(store, make_doc, "d1")
    store.insert_observation(
        Observation(
            observation_id="o1", document_id="d1", metric_id="station_count",
            entity_id="特来电", value=100.0, unit="", period_start=T0,
            period_end=T2, region=None, confidence=0.9, evidence_text="e",
        )
    )
    store.insert_observation(
        Observation(
            observation_id="o2", document_id="d1", metric_id="price",
            entity_id="特来电", value=1.0, unit="元", period_start=T0,
            period_end=T2, region=None, confidence=0.9, evidence_text="e",
        )
    )
    rows = store.query_observations_in_range(
        "t1", metric_id="station_count", entity_id="特来电"
    )
    assert [r["observation_id"] for r in rows] == ["o1"]


def test_query_prior_runs_orders_by_start(make_doc) -> None:
    store = SQLiteStore(":memory:")
    for rid, started in (("r1", T0), ("r2", T1)):
        store.insert_run(rid, "t1", "tk1", started)
        store.complete_run(rid, status="success")
    rows = store.query_prior_runs("t1", limit=1)
    assert [r["run_id"] for r in rows] == ["r2"]


def test_count_events_by_type(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电"])
    _insert_event(store, "e2", "new_product", T2, ["特来电"])
    _insert_event(store, "e3", "financing", T2, ["特来电"])
    counts = store.count_events_by_type("t1")
    assert counts == {"new_product": 2, "financing": 1}
    entity_counts = store.count_events_by_type("t1", entity_id="特来电")
    assert entity_counts == {"new_product": 2, "financing": 1}
    other_counts = store.count_events_by_type("t1", entity_id="星星充电")
    assert other_counts == {}


def test_complete_run_analysis_fields(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T0)
    store.complete_run(
        "r1", status="success", analysis_claims=5, evidence_coverage=0.8
    )
    row = store._conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["analysis_claims"] == 5
    assert row["evidence_coverage"] == 0.8


def test_events_store_entity_ids(make_doc) -> None:
    store = SQLiteStore(":memory:")
    _insert_event(store, "e1", "new_product", T1, ["特来电", "星星充电"])
    row = store._conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
    assert row["entity_ids"] == '["特来电", "星星充电"]'
