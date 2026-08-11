"""历史比较：比较窗口 + 7 项趋势指标的三点比较（Phase 3）。

窗口基于 TaskConfig.window.days（默认 7 天，即周度），ISO 时间字符串比较，
与 SQLite 中 event_date / period_end 的存储格式一致。

趋势指标由 HistoricalComparison 计算，全部确定性（SQL 聚合 + 权重公式），
不依赖 LLM；每个指标输出 current / last / 4w-avg 三点比较。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from industry_intelligence.analysis.base import _as_float_value, _row_value
from industry_intelligence.analysis.models import (
    TREND_CHANNEL_CHANGE,
    TREND_EVENT_VELOCITY,
    TREND_MAJOR_PROJECT_GROWTH,
    TREND_NEGATIVE_RISK_CHANGE,
    TREND_PRICE_CHANGE,
    TREND_SHARE_OF_VOICE,
    TREND_TECH_HEAT_CHANGE,
    TrendIndicator,
)
from industry_intelligence.config.models import TaskConfig, TopicProfile
from industry_intelligence.storage import SQLiteStore

WINDOW_CURRENT = "current"
WINDOW_LAST = "last"
WINDOW_LAST_4W = "last_4w"
WINDOW_LAST_12W = "last_12w"
WINDOW_LAST_52W = "last_52w"

WINDOW_KEYS = (
    WINDOW_CURRENT,
    WINDOW_LAST,
    WINDOW_LAST_4W,
    WINDOW_LAST_12W,
    WINDOW_LAST_52W,
)

# 重大项目事件类型（major_project_growth 信号）
MAJOR_PROJECT_EVENT_TYPES = (
    "bid_order",
    "investment_expansion",
    "capacity_build",
    "m_and_a",
    "cooperation",
)

# 渠道扩张信号事件类型（channel_change 信号）
CHANNEL_EVENT_TYPES = ("channel_expansion", "cooperation")

#: 趋势比较基准窗口跨度（周）
TREND_WINDOW_WEEKS = 4


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _ref_time(reference_date: str | None) -> datetime:
    return (
        datetime.now(UTC)
        if reference_date is None
        else datetime.fromisoformat(reference_date)
    )


def compute_comparison_windows(
    task: TaskConfig,
    reference_date: str | None = None,
) -> dict[str, tuple[str, str]]:
    """计算 5 个比较窗口的 (start, end) ISO 时间闭区间。

    reference_date 缺省取 UTC now（可传固定值便于测试）。
    """
    ref = _ref_time(reference_date)
    days = max(task.window.days, 1)

    return {
        WINDOW_CURRENT: (_iso(ref - timedelta(days=days)), _iso(ref)),
        WINDOW_LAST: (
            _iso(ref - timedelta(days=2 * days)),
            _iso(ref - timedelta(days=days)),
        ),
        WINDOW_LAST_4W: (_iso(ref - timedelta(days=4 * days)), _iso(ref)),
        WINDOW_LAST_12W: (_iso(ref - timedelta(days=12 * days)), _iso(ref)),
        WINDOW_LAST_52W: (_iso(ref - timedelta(days=52 * days)), _iso(ref)),
    }


def compute_baseline_window(
    task: TaskConfig,
    reference_date: str | None = None,
) -> tuple[str, str]:
    """4 周基准窗口：当前周开始之前的 4×days 时间跨度（不含当前周）。

    作为 trend 指标的 baseline_avg 参照；与 WINDOW_LAST_4W（滚动 4 周含当前）
    不同，本窗口是纯历史基准。
    """
    ref = _ref_time(reference_date)
    days = max(task.window.days, 1)
    return (_iso(ref - timedelta(days=5 * days)), _iso(ref - timedelta(days=days)))


class HistoricalComparison:
    """历史趋势比较：对主题做 7 项指标的三点比较（current / last / 4w-avg）。

    全部指标确定性计算，不依赖 LLM。share_of_voice 按主题实体各输出一条
    TrendIndicator，其余指标各输出一条。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        task: TaskConfig,
        topic: TopicProfile,
        reference_date: str | None = None,
    ) -> None:
        self._store = sqlite_store
        self._task = task
        self._topic = topic
        self._windows = compute_comparison_windows(task, reference_date)
        self._baseline = compute_baseline_window(task, reference_date)

    # ------------------------------------------------------------- 对外接口

    def compute_trends(
        self, topic_id: str | None = None
    ) -> dict[str, list[TrendIndicator]]:
        """计算全部趋势指标，返回 {indicator_name: [TrendIndicator, ...]}。"""
        tid = topic_id or self._topic.id
        return {
            TREND_EVENT_VELOCITY: [self._event_velocity(tid)],
            TREND_SHARE_OF_VOICE: self._share_of_voice(tid),
            TREND_MAJOR_PROJECT_GROWTH: [self._major_project_growth(tid)],
            TREND_TECH_HEAT_CHANGE: [self._tech_heat_change(tid)],
            TREND_PRICE_CHANGE: [self._price_change(tid)],
            TREND_CHANNEL_CHANGE: [self._channel_change(tid)],
            TREND_NEGATIVE_RISK_CHANGE: [self._negative_risk_change(tid)],
        }

    # ------------------------------------------------------------- 单指标计算

    def _event_velocity(self, tid: str) -> TrendIndicator:
        """每时间单位的事件数变化（事件/天）。"""
        days = max(self._task.window.days, 1)
        cur = (
            len(self._store.query_events_in_range(tid, *self._windows[WINDOW_CURRENT]))
            / days
        )
        prev = (
            len(self._store.query_events_in_range(tid, *self._windows[WINDOW_LAST]))
            / days
        )
        base = len(self._store.query_events_in_range(tid, *self._baseline)) / (
            4 * days
        )
        return self._trend(TREND_EVENT_VELOCITY, cur, prev, base)

    def _share_of_voice(self, tid: str) -> list[TrendIndicator]:
        """各品牌在主题事件中的占比变化（每实体一条）。"""
        entities = [c.canonical_name for c in self._topic.entities.companies]
        if not entities:
            return []
        totals = {
            label: len(self._store.query_events_in_range(tid, start, end))
            for label, (start, end) in (
                (WINDOW_CURRENT, self._windows[WINDOW_CURRENT]),
                (WINDOW_LAST, self._windows[WINDOW_LAST]),
                ("baseline", self._baseline),
            )
        }
        out: list[TrendIndicator] = []
        for ent in entities:
            current = self._entity_share(
                tid, ent, *self._windows[WINDOW_CURRENT], totals[WINDOW_CURRENT]
            )
            previous = self._entity_share(
                tid, ent, *self._windows[WINDOW_LAST], totals[WINDOW_LAST]
            )
            baseline = self._entity_share(
                tid, ent, *self._baseline, totals["baseline"]
            )
            out.append(
                self._trend(
                    TREND_SHARE_OF_VOICE,
                    current,
                    previous,
                    baseline,
                    entity_id=ent,
                )
            )
        return out

    def _entity_share(
        self, tid: str, entity: str, start: str, end: str, total: int
    ) -> float:
        if total <= 0:
            return 0.0
        count = len(
            self._store.query_events_by_entity(tid, entity, start, end)
        )
        return count / total

    def _major_project_growth(self, tid: str) -> TrendIndicator:
        """重大项目数量变化（周级数量；4w 基准为每周平均）。"""
        cur = float(
            self._count_types(tid, *self._windows[WINDOW_CURRENT], MAJOR_PROJECT_EVENT_TYPES)
        )
        prev = float(
            self._count_types(tid, *self._windows[WINDOW_LAST], MAJOR_PROJECT_EVENT_TYPES)
        )
        base = (
            self._count_types(tid, *self._baseline, MAJOR_PROJECT_EVENT_TYPES)
            / TREND_WINDOW_WEEKS
        )
        return self._trend(TREND_MAJOR_PROJECT_GROWTH, cur, prev, base)

    def _tech_heat_change(self, tid: str) -> TrendIndicator:
        """技术热度 delta：复用 THI 公式；4w 基准取每周平均热度（近似 /4）。"""
        from industry_intelligence.analysis.technology import (
            TECH_EVENT_TYPES,
            compute_thi,
        )

        def heat(start: str, end: str) -> float:
            events: list[object] = []
            for etype in TECH_EVENT_TYPES:
                events.extend(
                    self._store.query_events_in_range(
                        tid, start, end, event_type_id=etype
                    )
                )
            return compute_thi(
                events, self._count_keyword_docs(tid, start, end), start, end
            ).score

        cur = heat(*self._windows[WINDOW_CURRENT])
        prev = heat(*self._windows[WINDOW_LAST])
        base = heat(*self._baseline) / TREND_WINDOW_WEEKS
        return self._trend(TREND_TECH_HEAT_CHANGE, cur, prev, base)

    def _price_change(self, tid: str) -> TrendIndicator:
        """价格观测均值变化（price 指标观测平均值）。"""
        cur = self._price_avg(tid, *self._windows[WINDOW_CURRENT])
        prev = self._price_avg(tid, *self._windows[WINDOW_LAST])
        base = self._price_avg(tid, *self._baseline)
        return self._trend(TREND_PRICE_CHANGE, cur, prev, base)

    def _price_avg(self, tid: str, start: str, end: str) -> float:
        obs = self._store.query_observations_in_range(
            tid, metric_id="price", start_date=start, end_date=end
        )
        values = [_as_float_value(_row_value(o, "value", 0.0), 0.0) for o in obs]
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _channel_change(self, tid: str) -> TrendIndicator:
        """渠道扩张信号变化（周级数量；4w 基准为每周平均）。"""
        cur = float(
            self._count_types(tid, *self._windows[WINDOW_CURRENT], CHANNEL_EVENT_TYPES)
        )
        prev = float(
            self._count_types(tid, *self._windows[WINDOW_LAST], CHANNEL_EVENT_TYPES)
        )
        base = (
            self._count_types(tid, *self._baseline, CHANNEL_EVENT_TYPES)
            / TREND_WINDOW_WEEKS
        )
        return self._trend(TREND_CHANNEL_CHANGE, cur, prev, base)

    def _negative_risk_change(self, tid: str) -> TrendIndicator:
        """风险事件频次 delta（周级数量；4w 基准为每周平均）。"""
        from industry_intelligence.analysis.risk import RISK_EVENT_TYPES

        cur = float(
            self._count_types(tid, *self._windows[WINDOW_CURRENT], RISK_EVENT_TYPES)
        )
        prev = float(
            self._count_types(tid, *self._windows[WINDOW_LAST], RISK_EVENT_TYPES)
        )
        base = (
            self._count_types(tid, *self._baseline, RISK_EVENT_TYPES)
            / TREND_WINDOW_WEEKS
        )
        return self._trend(TREND_NEGATIVE_RISK_CHANGE, cur, prev, base)

    # ------------------------------------------------------------- 共享助手

    def _count_types(
        self, tid: str, start: str, end: str, etypes: Sequence[str]
    ) -> int:
        total = 0
        for etype in etypes:
            total += len(
                self._store.query_events_in_range(
                    tid, start, end, event_type_id=etype
                )
            )
        return total

    def _count_keyword_docs(self, tid: str, start: str, end: str) -> int:
        """窗口内命中技术关键词（topic.keywords.technology）的文档数。"""
        tech_keywords = set(self._topic.keywords.technology)
        if not tech_keywords:
            return 0
        count = 0
        for row in self._store.query_documents_in_range(tid, start, end):
            try:
                matched = set(json.loads(row["matched_keywords"] or "[]"))
            except (ValueError, TypeError):
                matched = set()
            if matched & tech_keywords:
                count += 1
        return count

    def _trend(
        self,
        indicator_name: str,
        current: float,
        previous: float,
        baseline: float,
        entity_id: str | None = None,
    ) -> TrendIndicator:
        delta = current - previous
        delta_pct = (delta / previous * 100.0) if previous else 0.0
        return TrendIndicator(
            indicator_name=indicator_name,
            current_value=round(float(current), 4),
            previous_value=round(float(previous), 4),
            delta=round(float(delta), 4),
            delta_pct=round(float(delta_pct), 4),
            window_weeks=TREND_WINDOW_WEEKS,
            baseline_avg=round(float(baseline), 4),
            entity_id=entity_id,
        )
