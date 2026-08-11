"""HistoricalComparison 单元测试：7 项趋势指标的三点比较。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industry_intelligence.analysis.historical import (
    HistoricalComparison,
    compute_baseline_window,
    compute_comparison_windows,
)
from industry_intelligence.analysis.models import (
    TREND_CHANNEL_CHANGE,
    TREND_EVENT_VELOCITY,
    TREND_INDICATORS,
    TREND_MAJOR_PROJECT_GROWTH,
    TREND_NEGATIVE_RISK_CHANGE,
    TREND_PRICE_CHANGE,
    TREND_SHARE_OF_VOICE,
    TREND_TECH_HEAT_CHANGE,
)
from industry_intelligence.config.models import TopicKeywords
from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics.models import Observation
from industry_intelligence.storage import SQLiteStore

# 固定参考时间，保证窗口确定性（与 sample_task 的 days=7 配合）
REF = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
REF_ISO = REF.isoformat(timespec="seconds")


def _iso(offset_days: int) -> str:
    return (REF - timedelta(days=offset_days)).isoformat(timespec="seconds")


def _event(eid: str, etype: str, offset: int, entity: str = "特来电") -> Event:
    return Event(
        event_id=eid,
        event_type_id=etype,
        title=f"{eid}{etype}",
        event_date=_iso(offset),
        summary="摘要",
        document_ids=["d_ev"],
        entity_ids=[entity],
        confidence=1.0,
        topic_id="t1",
    )


def _comparison(store, sample_topic, sample_task) -> HistoricalComparison:
    return HistoricalComparison(
        store, sample_task, sample_topic, reference_date=REF_ISO
    )


def _store(
    make_doc,
    events: list[Event] | None = None,
    observations: list[Observation] | None = None,
    docs: list[object] | None = None,
) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", _iso(0))
    # 事件统一引用该文档，避免 event_documents 外键失败
    store.insert_document(make_doc(document_id="d_ev", title="事件文档", fetched_at=_iso(1)))
    for doc in docs or []:
        store.insert_document(doc)
    for ev in events or []:
        store.insert_event(ev)
    for obs in observations or []:
        store.insert_observation(obs)
    return store


def _tech_topic(sample_topic):
    return replace(
        sample_topic,
        keywords=TopicKeywords(
            core=sample_topic.keywords.core,
            technology=["超充", "液冷"],
            events=sample_topic.keywords.events,
        ),
    )


# ---------------------------------------------------------------------------
# 窗口计算
# ---------------------------------------------------------------------------


def _task():
    from industry_intelligence.config.models import TaskConfig

    return TaskConfig(id="tk1", topic_id="t1", enabled=True)


def test_compute_baseline_window_excludes_current() -> None:
    start, end = compute_baseline_window(_task(), reference_date=REF_ISO)
    assert start < end
    # 基准窗口 = 当前周之前的 4 周，结束于当前周起点
    assert end == _iso(7)
    assert start == _iso(35)


def test_comparison_windows_relationships() -> None:
    windows = compute_comparison_windows(_task(), reference_date=REF_ISO)
    cur = windows["current"]
    last = windows["last"]
    assert cur[0] == _iso(7)
    assert cur[1] == _iso(0)
    assert last[0] == _iso(14)
    assert last[1] == _iso(7)


# ---------------------------------------------------------------------------
# 单指标
# ---------------------------------------------------------------------------


def test_event_velocity(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        events=[
            _event("e1", "policy_regulation", 1),
            _event("e2", "bid_order", 3),          # 当前 2 条
            _event("e3", "policy_regulation", 10),  # 上周 1 条（同时计入基准）
            _event("e4", "policy_regulation", 16),
            _event("e5", "bid_order", 22),
            _event("e6", "policy_regulation", 28),  # 4w 基准共 4 条
        ],
    )
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_EVENT_VELOCITY
    ][0]
    assert t.indicator_name == TREND_EVENT_VELOCITY
    assert t.current_value == pytest.approx(2 / 7, abs=1e-4)
    assert t.previous_value == pytest.approx(1 / 7, abs=1e-4)
    assert t.baseline_avg == pytest.approx(1 / 7, abs=1e-4)
    assert t.delta_pct == pytest.approx(100.0, abs=1e-4)
    assert t.window_weeks == 4


def test_share_of_voice_per_entity(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        events=[
            _event("e1", "bid_order", 1, entity="特来电"),
            _event("e2", "policy_regulation", 3, entity="特来电"),
            _event("e3", "bid_order", 2, entity="星星充电"),  # 当前共 3
            _event("e4", "bid_order", 10, entity="特来电"),     # 上周共 1
            _event("e5", "bid_order", 16, entity="特来电"),
            _event("e6", "bid_order", 22, entity="星星充电"),
            _event("e7", "policy_regulation", 28, entity="星星充电"),  # 4w 共 4
        ],
    )
    trends = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_SHARE_OF_VOICE
    ]
    assert len(trends) == 2
    by_entity = {t.entity_id: t for t in trends}
    t1 = by_entity["特来电"]
    assert t1.current_value == pytest.approx(2 / 3, abs=1e-4)
    assert t1.previous_value == 1.0
    assert t1.baseline_avg == pytest.approx(0.5, abs=1e-4)
    t2 = by_entity["星星充电"]
    assert t2.current_value == pytest.approx(1 / 3, abs=1e-4)
    assert t2.previous_value == 0.0
    assert t2.delta_pct == 0.0  # 上周无该实体事件 → 变化率按 0 处理


def test_major_project_growth(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        events=[
            _event("e1", "bid_order", 1),
            _event("e2", "investment_expansion", 3),  # 当前 2
            _event("e3", "bid_order", 10),              # 上周 1（同时计入基准）
            _event("e4", "bid_order", 16),
            _event("e5", "investment_expansion", 22),
            _event("e6", "capacity_build", 28),         # 4w 共 4 → 每周均 1
        ],
    )
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_MAJOR_PROJECT_GROWTH
    ][0]
    assert t.current_value == 2.0
    assert t.previous_value == 1.0
    assert t.baseline_avg == 1.0
    assert t.delta == 1.0
    assert t.delta_pct == 100.0


def test_tech_heat_change(make_doc, sample_topic, sample_task) -> None:
    topic = _tech_topic(sample_topic)
    store = _store(
        make_doc,
        events=[
            _event("e1", "new_product", 1),
            _event("e2", "technology_rd", 3),   # 当前：2.0 + 1.5
            _event("e3", "new_product", 10),    # 上周：2.0（同时计入基准）
            _event("e4", "new_product", 16),
            _event("e5", "new_product", 22),
            _event("e6", "new_product", 28),    # 4w 共 4 × 2.0
        ],
        docs=[
            make_doc(
                document_id="dk1", title="特来电超充新品", fetched_at=_iso(2),
                matched_keywords=["超充"], matched_entities=["特来电"],
            ),
            make_doc(
                document_id="dk2", title="液冷充电桩", fetched_at=_iso(15),
                matched_keywords=["液冷"], matched_entities=["特来电"],
            ),
            make_doc(
                document_id="dk3", title="超充升级", fetched_at=_iso(28),
                matched_keywords=["超充"], matched_entities=["特来电"],
            ),
        ],
    )
    t = _comparison(store, topic, sample_task).compute_trends()[
        TREND_TECH_HEAT_CHANGE
    ][0]
    # THI = 10×Σ权重 + 0.5×关键词文档
    # 当前：10×(2.0+1.5)+0.5×1=35.5；上周：10×2.0=20.0
    # 4w：10×(2.0×4)+0.5×2=81 → /4 = 20.25
    assert t.current_value == pytest.approx(35.5, abs=1e-4)
    assert t.previous_value == pytest.approx(20.0, abs=1e-4)
    assert t.baseline_avg == pytest.approx(20.25, abs=1e-4)
    assert t.delta_pct == pytest.approx(77.5, abs=1e-4)


def test_price_change(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        docs=[make_doc(document_id="dp", title="价格观测", fetched_at=_iso(1))],
        observations=[
            Observation(
                observation_id="o1", document_id="dp", metric_id="price",
                entity_id="特来电", value=110.0, unit="元", period_start=_iso(7),
                period_end=_iso(3), region=None, confidence=0.9, evidence_text="e",
            ),
            Observation(
                observation_id="o2", document_id="dp", metric_id="price",
                entity_id="特来电", value=100.0, unit="元", period_start=_iso(14),
                period_end=_iso(12), region=None, confidence=0.9, evidence_text="e",
            ),
            Observation(
                observation_id="o3", document_id="dp", metric_id="price",
                entity_id="特来电", value=107.5, unit="元", period_start=_iso(22),
                period_end=_iso(16), region=None, confidence=0.9, evidence_text="e",
            ),
            Observation(
                observation_id="o4", document_id="dp", metric_id="price",
                entity_id="特来电", value=107.5, unit="元", period_start=_iso(28),
                period_end=_iso(22), region=None, confidence=0.9, evidence_text="e",
            ),
        ],
    )
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_PRICE_CHANGE
    ][0]
    # 当前 110 / 上周 100 / 4w 平均 (100 + 107.5 + 107.5)/3 = 105
    assert t.current_value == 110.0
    assert t.previous_value == 100.0
    assert t.baseline_avg == 105.0
    assert t.delta_pct == 10.0


def test_channel_change(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        events=[
            _event("e1", "channel_expansion", 1),
            _event("e2", "channel_expansion", 3),  # 当前 2
            _event("e3", "channel_expansion", 10),  # 上周 1（同时计入基准）
            _event("e4", "channel_expansion", 16),
            _event("e5", "channel_expansion", 22),
            _event("e6", "channel_expansion", 28),  # 4w 共 4
        ],
    )
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_CHANNEL_CHANGE
    ][0]
    assert t.current_value == 2.0
    assert t.previous_value == 1.0
    assert t.baseline_avg == 1.0
    assert t.delta_pct == 100.0


def test_negative_risk_change(make_doc, sample_topic, sample_task) -> None:
    store = _store(
        make_doc,
        events=[
            _event("e1", "recall_accident", 1),
            _event("e2", "litigation_compliance", 3),  # 当前 2
            _event("e3", "recall_accident", 10),        # 上周 1（同时计入基准）
            _event("e4", "recall_accident", 16),
            _event("e5", "litigation_compliance", 22),
            _event("e6", "recall_accident", 28),        # 4w 共 4
        ],
    )
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_NEGATIVE_RISK_CHANGE
    ][0]
    assert t.current_value == 2.0
    assert t.previous_value == 1.0
    assert t.baseline_avg == 1.0
    assert t.delta == 1.0


# ---------------------------------------------------------------------------
# 聚合行为
# ---------------------------------------------------------------------------


def test_compute_trends_returns_all_seven(make_doc, sample_topic, sample_task) -> None:
    store = _store(make_doc, events=[_event("e1", "bid_order", 1)])
    result = _comparison(store, sample_topic, sample_task).compute_trends()
    assert set(result.keys()) == TREND_INDICATORS


def test_empty_store_all_zero(make_doc, sample_topic, sample_task) -> None:
    store = _store(make_doc)
    result = _comparison(store, sample_topic, sample_task).compute_trends()
    for name, items in result.items():
        assert items, f"{name} 应至少有一条 TrendIndicator"
        for t in items:
            assert t.current_value == 0.0, name
            assert t.previous_value == 0.0, name
            assert t.baseline_avg == 0.0, name
            assert t.delta == 0.0, name
            assert t.delta_pct == 0.0, name


def test_delta_pct_zero_when_previous_empty(
    make_doc, sample_topic, sample_task
) -> None:
    store = _store(make_doc, events=[_event("e1", "bid_order", 1)])
    t = _comparison(store, sample_topic, sample_task).compute_trends()[
        TREND_EVENT_VELOCITY
    ][0]
    assert t.current_value == pytest.approx(1 / 7, abs=1e-4)
    assert t.previous_value == 0.0
    assert t.delta_pct == 0.0  # 除零保护


def test_share_of_voice_no_entities(
    make_doc, sample_topic, sample_task
) -> None:
    topic = replace(sample_topic, entities=replace(sample_topic.entities, companies=[]))
    store = _store(make_doc, events=[_event("e1", "bid_order", 1)])
    trends = _comparison(store, topic, sample_task).compute_trends()[
        TREND_SHARE_OF_VOICE
    ]
    assert trends == []
