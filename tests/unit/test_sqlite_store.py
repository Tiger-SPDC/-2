"""SQLite 存储层单元测试（全部 :memory:）。"""

from __future__ import annotations

import sqlite3

import pytest

from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics.models import Observation
from industry_intelligence.storage import SQLiteStore

TABLES = {
    "runs",
    "documents",
    "entities",
    "entity_aliases",
    "events",
    "event_documents",
    "observations",
}


def _table_names(store: SQLiteStore) -> set[str]:
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_create_all_tables() -> None:
    store = SQLiteStore(":memory:")
    assert _table_names(store) >= TABLES


def test_rebuild_idempotent() -> None:
    store = SQLiteStore(":memory:")
    store.rebuild()
    store.rebuild()
    assert _table_names(store) >= TABLES


def test_insert_query_document(make_doc) -> None:
    store = SQLiteStore(":memory:")
    doc = make_doc(document_id="d1", title="标题", content_text="正文", matched_entities=["特来电"])
    store.insert_document(doc)
    rows = store._conn.execute("SELECT * FROM documents").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "标题"
    assert rows[0]["matched_entities"] == '["特来电"]'


def test_reinsert_document_preserves_evidence_links(make_doc) -> None:
    """回归：INSERT OR REPLACE 会 DELETE+INSERT，触发 claim_evidence.document_id
    ON DELETE SET NULL，observation_id 也为空时违反 CHECK。upsert 原地更新，
    不得抛错且证据链接保留。"""
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="标题"))
    store.insert_run("r1", "t1", "tk1", "2026-08-01T00:00:00+00:00")
    store.insert_claim(
        "c1", "结论", "fact", 0.9, "competitor", "t1", "r1"
    )
    store.insert_claim_evidence("c1", document_id="d1")
    # 模拟重采集：同一 document_id 再次写入（之前会触发 CHECK 约束失败）
    store.insert_document(make_doc(document_id="d1", title="标题"))
    ev = store.query_claim_evidence("c1")
    assert len(ev) == 1
    assert ev[0]["document_id"] == "d1"
    assert ev[0]["observation_id"] is None


def test_insert_entity_with_aliases() -> None:
    store = SQLiteStore(":memory:")
    store.insert_entity("特来电", "特来电", ["特来电新能源", "TLD"], topic_id="t1")
    entity = store._conn.execute("SELECT * FROM entities").fetchone()
    assert entity["canonical_name"] == "特来电"
    aliases = {a["alias"] for a in store._conn.execute("SELECT * FROM entity_aliases")}
    assert aliases == {"特来电新能源", "TLD"}


def test_insert_event_and_query(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="标题"))
    store.insert_event(
        Event(
            event_id="e1",
            event_type_id="financing",
            title="标题",
            event_date="2026-08-01T00:00:00+00:00",
            summary="摘要",
            document_ids=["d1"],
            entity_ids=["特来电"],
            confidence=0.9,
            topic_id="t1",
        )
    )
    events = store.query_events("t1")
    assert len(events) == 1
    assert events[0]["event_type_id"] == "financing"
    joins = store._conn.execute("SELECT * FROM event_documents").fetchall()
    assert len(joins) == 1


def test_query_events_by_type(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="标题"))
    for eid, etype in (("e1", "financing"), ("e2", "other")):
        store.insert_event(
            Event(
                event_id=eid,
                event_type_id=etype,
                title="标题",
                event_date="2026-08-01",
                summary="s",
                document_ids=["d1"],
                entity_ids=[],
                confidence=1.0,
                topic_id="t1",
            )
        )
    assert len(store.query_events("t1", event_type_id="financing")) == 1
    assert len(store.query_events("t1", event_type_id="other")) == 1


def test_insert_observation_and_query(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="标题"))
    store.insert_observation(
        Observation(
            observation_id="o1",
            document_id="d1",
            metric_id="station_count",
            entity_id="特来电",
            value=100.0,
            unit="座",
            period_start=None,
            period_end=None,
            region=None,
            confidence=0.9,
            evidence_text="原文证据",
        )
    )
    rows = store.query_observations("t1")
    assert len(rows) == 1
    assert rows[0]["value"] == 100.0


def test_query_observations_by_metric(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="标题"))
    for mid, val in (("station_count", 100.0), ("charger_count", 200.0)):
        store.insert_observation(
            Observation(
                observation_id=f"o-{mid}",
                document_id="d1",
                metric_id=mid,
                entity_id="特来电",
                value=val,
                unit="",
                period_start=None,
                period_end=None,
                region=None,
                confidence=0.9,
                evidence_text="e",
            )
        )
    assert len(store.query_observations("t1", metric_id="station_count")) == 1
    assert len(store.query_observations("t1")) == 2


def test_run_lifecycle() -> None:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", "2026-08-01T00:00:00+00:00")
    store.complete_run(
        "r1",
        status="success",
        documents_collected=3,
        observations_extracted=2,
        errors=[],
    )
    row = store._conn.execute("SELECT * FROM runs WHERE run_id='r1'").fetchone()
    assert row["status"] == "success"
    assert row["documents_collected"] == 3
    assert row["observations_extracted"] == 2
    assert row["finished_at"] is not None


def test_event_document_foreign_key_enforced() -> None:
    store = SQLiteStore(":memory:")
    event = Event(
        event_id="e1",
        event_type_id="financing",
        title="t",
        event_date="2026-08-01",
        summary="s",
        document_ids=["missing_doc"],
        entity_ids=[],
        confidence=1.0,
        topic_id="t1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_event(event)


def test_drop_all_removes_tables() -> None:
    store = SQLiteStore(":memory:")
    store.insert_entity("特来电", "特来电", [], "t1")
    store.drop_all()
    assert TABLES.isdisjoint(_table_names(store))


def test_query_unknown_topic_returns_empty(make_doc) -> None:
    store = SQLiteStore(":memory:")
    store.insert_document(make_doc(document_id="d1", title="t"))
    assert store.query_events("no_such_topic") == []
    assert store.query_observations("no_such_topic") == []
