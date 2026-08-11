"""事件聚类器单元测试：相似度 + 共享实体 + 时间接近。"""

from __future__ import annotations

import pytest

from industry_intelligence.intelligence import EventClusterer

T1 = "2026-08-01T00:00:00+00:00"
T2 = "2026-08-02T00:00:00+00:00"
T_FAR = "2026-08-10T00:00:00+00:00"

TITLE = "特来电发布液冷超充新品"


def _doc(make_doc, document_id, title, published_at, entities):
    return make_doc(
        document_id=document_id,
        title=title,
        published_at=published_at,
        matched_entities=entities,
    )


@pytest.fixture
def clusterer() -> EventClusterer:
    return EventClusterer()


def test_merge_similar_docs(clusterer, make_doc) -> None:
    d1 = _doc(make_doc, "d1", TITLE, T1, ["特来电"])
    d2 = _doc(make_doc, "d2", TITLE, T2, ["特来电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 1
    assert events[0].document_ids == ["d1", "d2"]


def test_distinct_when_unrelated(clusterer, make_doc) -> None:
    d1 = _doc(make_doc, "d1", TITLE, T1, ["特来电"])
    d2 = _doc(make_doc, "d2", "星星充电公布财报数据", T2, ["星星充电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 2


def test_requires_shared_entity(clusterer, make_doc) -> None:
    title = "充电桩保有量创历史新高"
    d1 = _doc(make_doc, "d1", title, T1, ["特来电"])
    d2 = _doc(make_doc, "d2", title, T2, ["星星充电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 2


def test_requires_time_proximity(clusterer, make_doc) -> None:
    d1 = _doc(make_doc, "d1", TITLE, T1, ["特来电"])
    d2 = _doc(make_doc, "d2", TITLE, T_FAR, ["特来电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 2


def test_missing_published_at_blocks_merge(clusterer, make_doc) -> None:
    d1 = make_doc(document_id="d1", title=TITLE, matched_entities=["特来电"])
    d2 = _doc(make_doc, "d2", TITLE, T2, ["特来电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 2


def test_empty_input(clusterer) -> None:
    assert clusterer.cluster([]) == []


def test_event_type_from_doc_map(clusterer, make_doc) -> None:
    d1 = _doc(make_doc, "d1", TITLE, T1, ["特来电"])
    events = clusterer.cluster([d1], {"d1": "new_product"})
    assert events[0].event_type_id == "new_product"


def test_event_aggregates_entities(clusterer, make_doc) -> None:
    title = "充电桩保有量破500万"
    d1 = _doc(make_doc, "d1", title, T1, ["特来电"])
    d2 = _doc(make_doc, "d2", title, T2, ["星星充电", "特来电"])
    events = clusterer.cluster([d1, d2])
    assert len(events) == 1
    assert set(events[0].entity_ids) == {"特来电", "星星充电"}


def test_event_id_stable_and_title_from_earliest(clusterer, make_doc) -> None:
    d1 = _doc(make_doc, "d1", TITLE, T1, ["特来电"])
    events = clusterer.cluster([d1])
    assert len(events[0].event_id) == 16
    assert events[0].event_date == T1
    assert events[0].title == TITLE
