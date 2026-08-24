"""报告数据构建器（Phase 4）：SQLite → 格式无关的 ReportDataBundle。

ReportDataBuilder 纯确定性查询（不依赖 LLM），把 Pipeline 的分析结果
（indices / trends / 覆盖率）与 SQLite 明细（events/observations/documents/
claims/reviews）组装成 3 种 formatter 共享的中间结构。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from industry_intelligence.analysis.base import _as_float_value, _row_value
from industry_intelligence.analysis.historical import (
    WINDOW_CURRENT,
    compute_comparison_windows,
)
from industry_intelligence.config.models import TaskConfig, TopicProfile
from industry_intelligence.storage import SQLiteStore

_MIN_ISO = "0001-01-01T00:00:00"
_MAX_ISO = "9999-12-31T23:59:59"


@dataclass
class ReportDataBundle:
    """一次运行的报表数据（3 种 formatter 的唯一输入）。"""

    run_id: str
    topic_id: str
    task_id: str
    status: str
    period_start: str
    period_end: str

    events: list[dict[str, object]] = field(default_factory=list)
    observations: list[dict[str, object]] = field(default_factory=list)
    documents: list[dict[str, object]] = field(default_factory=list)
    companies: list[dict[str, object]] = field(default_factory=list)
    claims: list[dict[str, object]] = field(default_factory=list)
    indices: list[dict[str, object]] = field(default_factory=list)
    trends: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    review_results: list[dict[str, object]] = field(default_factory=list)
    quality: dict[str, float] = field(default_factory=dict)
    # 当次运行 LLM 发现的动态热点话题（v0.7.0a6 起进入报表，摘要顶部展示）
    hot_topics: list[str] = field(default_factory=list)
    # 推送上屏门槛词表（v0.7.0a9 起）：focus_terms=core（标题必须命中其一），
    # exclude_terms=exclude（命中即从推送剔除）。均来自 TopicProfile，零硬编码。
    focus_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    # 早报提炼（v0.7.0a10）：event_id -> 关联文档正文（供回访/提炼用）
    event_body: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    # 早报提炼结果：event_id -> 一条简洁中文早报（LLM 生成，空 dict 表示未提炼）
    briefings: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ReportDataBuilder:
    """从 SQLite 与运行结果构建 ReportDataBundle。"""

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        topic: TopicProfile,
        task: TaskConfig,
    ) -> None:
        self._store = sqlite_store
        self._topic = topic
        self._task = task

    def build(
        self,
        run_id: str,
        *,
        analysis_claims: int = 0,
        evidence_coverage: float = 0.0,
        indices: Sequence[object] | None = None,
        trends: Mapping[str, Sequence[object]] | None = None,
        errors: Sequence[str] | None = None,
        hot_topics: Sequence[str] | None = None,
    ) -> ReportDataBundle:
        """组装报表数据。

        indices / trends 来自 Pipeline 的分析结果（IndexScore / TrendIndicator 等
        含 _row_value 可读字段的对象）；其余明细全部从 SQLite 查询。
        """
        windows = compute_comparison_windows(self._task)
        cur_start, cur_end = windows[WINDOW_CURRENT]
        run = self._query_run(run_id)

        bundle = ReportDataBundle(
            run_id=run_id,
            topic_id=self._topic.id,
            task_id=self._task.id,
            status=str(_row_value(run, "status", "unknown")),
            period_start=cur_start,
            period_end=cur_end,
            errors=list(errors or []),
            hot_topics=list(hot_topics or []),
            focus_terms=list(self._topic.keywords.core),
            exclude_terms=list(self._topic.keywords.exclude),
        )
        bundle.documents = self._query_documents(cur_start, cur_end)
        bundle.events = self._query_events(cur_start, cur_end)
        bundle.event_body = self._store.query_event_documents_map(
            self._topic.id, cur_start, cur_end
        )
        bundle.observations = self._query_observations()
        bundle.companies = self._build_companies()
        bundle.claims = self._query_claims(run_id)
        bundle.indices = [self._index_score(idx) for idx in indices or []]
        bundle.trends = {
            name: [self._trend_indicator(t) for t in items]
            for name, items in (trends or {}).items()
        }
        bundle.review_results = self._query_reviews(run_id)
        bundle.quality = self._quality_metrics(
            analysis_claims=analysis_claims,
            evidence_coverage=evidence_coverage,
            claims=bundle.claims,
            review_results=bundle.review_results,
            documents=bundle.documents,
            observations=bundle.observations,
        )
        return bundle

    # ------------------------------------------------------------------ 查询

    def _query_run(self, run_id: str) -> object | None:
        """从 runs 表按 run_id 查元信息（返回 Row 或 None）。"""
        for row in self._store.query_prior_runs(self._topic.id, limit=100):
            if str(_row_value(row, "run_id", "")) == run_id:
                return row
        return None

    def _query_events(
        self, start: str, end: str
    ) -> list[dict[str, object]]:
        return [
            {
                "event_id": _row_value(r, "event_id", ""),
                "event_type_id": _row_value(r, "event_type_id", ""),
                "title": _row_value(r, "title", ""),
                "event_date": _row_value(r, "event_date", ""),
                "summary": _row_value(r, "summary", ""),
                "confidence": _as_float_value(_row_value(r, "confidence", 0.0), 0.0),
                "entity_ids": json.loads(
                    str(_row_value(r, "entity_ids", "[]") or "[]")
                ),
            }
            for r in self._store.query_events_in_range(
                self._topic.id, start, end
            )
        ]

    def _query_observations(self) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for r in self._store.query_observations(self._topic.id):
            out.append(
                {
                    "observation_id": _row_value(r, "observation_id", ""),
                    "metric_id": _row_value(r, "metric_id", ""),
                    "entity_id": _row_value(r, "entity_id", ""),
                    "value": _as_float_value(_row_value(r, "value", 0.0), 0.0),
                    "unit": _row_value(r, "unit", ""),
                    "period_start": _row_value(r, "period_start", None),
                    "period_end": _row_value(r, "period_end", None),
                    "region": _row_value(r, "region", None),
                    "confidence": _as_float_value(_row_value(r, "confidence", 0.0), 0.0),
                    "evidence_text": _row_value(r, "evidence_text", ""),
                }
            )
        return out

    def _query_documents(
        self, start: str, end: str
    ) -> list[dict[str, object]]:
        return [
            {
                "document_id": _row_value(r, "document_id", ""),
                "title": _row_value(r, "title", ""),
                "source_id": _row_value(r, "source_id", ""),
                "source_grade": _row_value(r, "source_grade", ""),
                "published_at": _row_value(r, "published_at", None),
                "fetched_at": _row_value(r, "fetched_at", ""),
                "matched_entities": json.loads(
                    str(_row_value(r, "matched_entities", "[]") or "[]")
                ),
            }
            for r in self._store.query_documents_in_range(
                self._topic.id, start, end
            )
        ]

    def _build_companies(self) -> list[dict[str, object]]:
        return [
            {
                "name": c.canonical_name,
                "aliases": list(c.aliases),
            }
            for c in self._topic.entities.companies
        ]

    def _canonicalize_entity(self, entity_id: object) -> object:
        """把 claim 的 entity_id 归一到跟踪企业的 canonical_name（别名 → 标准名）。

        映射全部来自 TopicProfile 配置（零硬编码）；非跟踪企业（如 LLM 新标注的
        "蔚来"）直接信任原值。这样"特来电新能源"不会与"特来电"在企业节重复。
        """
        if not isinstance(entity_id, str) or not entity_id:
            return entity_id
        folded = entity_id.casefold()
        for company in self._topic.entities.companies:
            for term in (company.canonical_name, *company.aliases):
                if folded == term.casefold():
                    return company.canonical_name
        return entity_id

    def _query_claims(self, run_id: str) -> list[dict[str, object]]:
        claims: dict[str, dict[str, object]] = {}
        for row in self._store.query_claims_with_evidence(run_id):
            claim_id = str(_row_value(row, "claim_id", ""))
            if not claim_id:
                continue
            entry = claims.setdefault(
                claim_id,
                {
                    "claim_id": claim_id,
                    "claim_text": _row_value(row, "claim_text", ""),
                    "claim_type": _row_value(row, "claim_type", "unknown"),
                    "confidence": _as_float_value(
                        _row_value(row, "confidence", 0.0), 0.0
                    ),
                    "entity_id": self._canonicalize_entity(
                        _row_value(row, "entity_id", None)
                    ),
                    "analysis_type": _row_value(row, "analysis_type", ""),
                    "evidence": [],
                },
            )
            evidence = entry["evidence"]
            if isinstance(evidence, list):
                evidence.append(
                    {
                        "document_id": _row_value(row, "document_id", None),
                        "observation_id": _row_value(row, "observation_id", None),
                        "evidence_role": _row_value(row, "evidence_role", ""),
                    }
                )
        return list(claims.values())

    def _query_reviews(self, run_id: str) -> list[dict[str, object]]:
        return [
            {
                "review_id": _row_value(r, "review_id", ""),
                "claim_id": _row_value(r, "claim_id", ""),
                "verdict": _row_value(r, "verdict", ""),
                "downgrade_to": _row_value(r, "downgrade_to", None),
                "issues": json.loads(str(_row_value(r, "issues", "[]") or "[]")),
                "reason": _row_value(r, "reason", ""),
            }
            for r in self._store.query_claim_reviews(run_id)
        ]

    # ------------------------------------------------------------------ 转换

    def _index_score(self, idx: object) -> dict[str, object]:
        return {
            "index_name": _row_value(idx, "index_name", ""),
            "entity_id": _row_value(idx, "entity_id", None),
            "score": _as_float_value(_row_value(idx, "score", 0.0), 0.0),
            "components": _row_value(idx, "components", {}) or {},
        }

    def _trend_indicator(self, t: object) -> dict[str, object]:
        return {
            "indicator_name": _row_value(t, "indicator_name", ""),
            "current_value": _as_float_value(_row_value(t, "current_value", 0.0), 0.0),
            "previous_value": _as_float_value(_row_value(t, "previous_value", 0.0), 0.0),
            "delta": _as_float_value(_row_value(t, "delta", 0.0), 0.0),
            "delta_pct": _as_float_value(_row_value(t, "delta_pct", 0.0), 0.0),
            "baseline_avg": _as_float_value(_row_value(t, "baseline_avg", 0.0), 0.0),
            "entity_id": _row_value(t, "entity_id", None),
        }

    def _quality_metrics(
        self,
        *,
        analysis_claims: int,
        evidence_coverage: float,
        claims: Sequence[dict[str, object]],
        review_results: Sequence[dict[str, object]],
        documents: Sequence[dict[str, object]],
        observations: Sequence[dict[str, object]],
    ) -> dict[str, float]:
        """数据质量指标（§25）：全部基于 bundle 内数据确定性计算。"""
        covered = sum(
            1
            for c in claims
            if isinstance(c.get("evidence"), list) and c["evidence"]
        )
        rejected = sum(
            1 for r in review_results if r.get("verdict") == "reject"
        )
        reviewed = len(review_results)
        return {
            "document_count": float(len(documents)),
            "event_count": float(len(self._store.query_events(self._topic.id))),
            "observation_count": float(len(observations)),
            "claim_count": float(len(claims)),
            "evidence_coverage": round(float(evidence_coverage), 4),
            "claims_with_evidence_rate": (
                round(covered / len(claims), 4) if claims else 0.0
            ),
            "review_count": float(reviewed),
            "review_reject_count": float(rejected),
            "review_reject_rate": (
                round(rejected / reviewed, 4) if reviewed else 0.0
            ),
            "analysis_claims": float(analysis_claims),
            "company_count": float(len(self._topic.entities.companies)),
        }
