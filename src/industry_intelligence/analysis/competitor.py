"""Competitor Analyst：企业竞争动态分析 + 竞争活动度指数（CAI）。

CAI 基于 SQL 聚合 + 事件类型权重，确定性计算、不依赖 LLM；
LLM 仅用于把事件数据合成为竞争动态结论（Claim + Evidence）。
"""

from __future__ import annotations

from collections.abc import Sequence

from industry_intelligence.analysis.base import (
    AnalysisAgent,
    _as_float_value,
    _row_value,
    build_claims_schema,
)
from industry_intelligence.analysis.historical import (
    WINDOW_CURRENT,
    WINDOW_LAST,
    compute_comparison_windows,
)
from industry_intelligence.analysis.models import (
    ANALYSIS_COMPETITOR,
    INDEX_CAI,
    AnalysisResult,
    IndexScore,
)

# 事件类型 → CAI 权重（默认映射；other 及未知类型取 0.5）
CAI_TYPE_WEIGHTS: dict[str, float] = {
    "bid_order": 3.0,
    "m_and_a": 3.0,
    "cooperation": 3.0,
    "new_product": 2.0,
    "investment_expansion": 2.0,
    "overseas_expansion": 2.0,
    "capacity_build": 1.5,
    "channel_expansion": 1.5,
}

#: 单个高权重事件（权重 3 × 置信度 1）× 10 = 30，数个重点事件即接近 100
_CAI_SCALE = 10.0

COMPETITOR_SCHEMA = build_claims_schema()


def compute_cai(
    events: Sequence[object],
    entity_id: str,
    period_start: str,
    period_end: str,
) -> IndexScore:
    """计算单个实体的竞争活动度指数（0-100，确定性）。

    公式：10 × Σ(事件类型权重 × 事件置信度)，封顶 100。
    components 记录各事件类型的加权贡献明细，便于审计。
    """
    components: dict[str, float] = {}
    total = 0.0
    for row in events:
        etype = str(_row_value(row, "event_type_id", "other"))
        confidence = _as_float_value(_row_value(row, "confidence", 1.0), 1.0)
        weight = CAI_TYPE_WEIGHTS.get(etype, 0.5) * confidence
        components[etype] = components.get(etype, 0.0) + weight
        total += weight
    score = min(100.0, _CAI_SCALE * total)
    return IndexScore(
        index_name=INDEX_CAI,
        entity_id=entity_id,
        score=round(score, 2),
        period_start=period_start,
        period_end=period_end,
        components=components,
    )


class CompetitorAnalyst(AnalysisAgent):
    """企业周度动态：竞争动作 / 战略意图 / 与上周比较。"""

    analysis_type = ANALYSIS_COMPETITOR

    def analyze(self, run_id: str) -> AnalysisResult:
        windows = compute_comparison_windows(self._task)
        cur_start, cur_end = windows[WINDOW_CURRENT]
        last_start, last_end = windows[WINDOW_LAST]
        errors: list[str] = []

        entities = [c.canonical_name for c in self._topic.entities.companies]
        if not entities:
            return AnalysisResult(
                ANALYSIS_COMPETITOR, cur_start, cur_end, errors=errors
            )

        # 确定性 CAI：每个企业一条（含零事件企业，便于横向比较）
        indices = [
            compute_cai(
                self._store.query_events_by_entity(
                    self._topic.id, entity, cur_start, cur_end
                ),
                entity,
                cur_start,
                cur_end,
            )
            for entity in entities
        ]

        if self._provider is None:
            return AnalysisResult(
                ANALYSIS_COMPETITOR, cur_start, cur_end, indices=indices,
                errors=errors,
            )

        prompt = self._build_prompt(entities, cur_start, cur_end, last_start, last_end)
        raw = self._generate_structured_safe(prompt, COMPETITOR_SCHEMA, errors)

        valid_docs, valid_obs = self._window_evidence_sets(cur_start, cur_end)

        def _fallback(entity: str | None) -> list[str]:
            return self._fallback_docs(entity, valid_docs, cur_start, cur_end)

        claims, evidences = self._extract_claims(
            raw,
            run_id,
            valid_docs=valid_docs,
            valid_obs=valid_obs,
            fallback_docs=_fallback,
            errors=errors,
        )

        return AnalysisResult(
            ANALYSIS_COMPETITOR, cur_start, cur_end, claims=claims,
            evidences=evidences, indices=indices, errors=errors,
        )

    # ------------------------------------------------------------------ 内部

    def _window_evidence_sets(
        self, period_start: str, period_end: str
    ) -> tuple[set[str], set[str]]:
        """当前窗口内真实存在的文档 / 观测 ID 集合（用于过滤 LLM 引用的证据）。"""
        docs = {
            row["document_id"]
            for row in self._store.query_documents_in_range(
                self._topic.id, period_start, period_end
            )
        }
        obs = {
            row["observation_id"]
            for row in self._store.query_observations_in_range(
                self._topic.id, start_date=period_start, end_date=period_end
            )
        }
        return docs, obs

    def _fallback_docs(
        self,
        entity_id: str | None,
        valid_docs: set[str],
        period_start: str,
        period_end: str,
    ) -> list[str]:
        """证据兜底：实体相关文档；无实体时用窗口内全部文档。"""
        if entity_id:
            ids = self._entity_document_ids(entity_id, period_start, period_end)
            if ids:
                return ids
        return sorted(valid_docs)

    def _build_prompt(
        self,
        entities: list[str],
        cur_start: str,
        cur_end: str,
        last_start: str,
        last_end: str,
    ) -> str:
        lines: list[str] = [f"分析窗口：{cur_start} 至 {cur_end}"]
        for entity in entities:
            current = self._store.query_events_by_entity(
                self._topic.id, entity, cur_start, cur_end
            )
            last = self._store.query_events_by_entity(
                self._topic.id, entity, last_start, last_end
            )
            docs = self._entity_document_ids(entity, cur_start, cur_end)
            lines.append(f"\n## 企业：{entity}")
            lines.append(self._format_events("本周事件", current))
            lines.append(self._format_events("上周事件", last))
            doc_ids = ", ".join(docs) if docs else "（无）"
            lines.append(f"本周相关文档 ID：{doc_ids}")
        return "\n".join(lines)

    @staticmethod
    def _format_events(label: str, events: Sequence[object]) -> str:
        if not events:
            return f"- {label}：（无）"
        parts = [f"- {label}（{len(events)} 条）："]
        for row in events:
            parts.append(
                f"  - [{_row_value(row, 'event_type_id', 'other')}] "
                f"{_row_value(row, 'title', '')} ({_row_value(row, 'event_date', '')}): "
                f"{_row_value(row, 'summary', '')}"
            )
        return "\n".join(parts)
