"""Technology Analyst：技术动态分析 + 技术热度指数（THI）。

THI 基于技术事件加权计数 + 技术关键词文档数，确定性计算；
LLM 仅用于把技术事件/关键词数据合成为技术结论。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from industry_intelligence.analysis.base import (
    AnalysisAgent,
    _as_float_value,
    _row_value,
    build_claims_schema,
)
from industry_intelligence.analysis.historical import (
    WINDOW_CURRENT,
    compute_comparison_windows,
)
from industry_intelligence.analysis.models import (
    ANALYSIS_TECHNOLOGY,
    INDEX_THI,
    AnalysisResult,
    IndexScore,
)

# 技术事件类型 → THI 权重
TECH_TYPE_WEIGHTS: dict[str, float] = {
    "new_product": 2.0,
    "technology_rd": 1.5,
    "capacity_build": 1.0,
}
TECH_EVENT_TYPES = tuple(TECH_TYPE_WEIGHTS.keys())

#: 单个高权重事件 × 10；关键词文档每篇 × 0.5
_THI_SCALE = 10.0
_KEYWORD_DOC_WEIGHT = 0.5

TECHNOLOGY_SCHEMA = build_claims_schema()


def compute_thi(
    events: Sequence[object],
    keyword_doc_count: int,
    period_start: str,
    period_end: str,
) -> IndexScore:
    """计算技术热度指数（0-100，确定性）。

    公式：10 × Σ(技术事件权重 × 置信度) + 0.5 × 技术关键词文档数，封顶 100。
    关键词文档贡献在加权事件贡献之外单独叠加（与计划公式一致）。
    """
    components: dict[str, float] = {}
    total = 0.0
    for row in events:
        etype = str(_row_value(row, "event_type_id", "other"))
        confidence = _as_float_value(_row_value(row, "confidence", 1.0), 1.0)
        weight = TECH_TYPE_WEIGHTS.get(etype, 0.5) * confidence
        components[etype] = components.get(etype, 0.0) + weight
        total += weight
    components["technology_keyword_docs"] = float(keyword_doc_count)
    score = min(
        100.0,
        _THI_SCALE * total + _KEYWORD_DOC_WEIGHT * keyword_doc_count,
    )
    return IndexScore(
        index_name=INDEX_THI,
        entity_id=None,
        score=round(score, 2),
        period_start=period_start,
        period_end=period_end,
        components=components,
    )


class TechnologyAnalyst(AnalysisAgent):
    """新品 / 技术路线 / 参数升级 / 技术热度 / 商业化。"""

    analysis_type = ANALYSIS_TECHNOLOGY

    def analyze(self, run_id: str) -> AnalysisResult:
        windows = compute_comparison_windows(self._task)
        cur_start, cur_end = windows[WINDOW_CURRENT]
        errors: list[str] = []

        tech_events: list[object] = []
        for etype in TECH_EVENT_TYPES:
            tech_events.extend(
                self._store.query_events_in_range(
                    self._topic.id, cur_start, cur_end, event_type_id=etype
                )
            )
        keyword_docs = self._count_keyword_docs(cur_start, cur_end)
        thi = compute_thi(tech_events, keyword_docs, cur_start, cur_end)

        if self._provider is None:
            return AnalysisResult(
                ANALYSIS_TECHNOLOGY, cur_start, cur_end, indices=[thi],
                errors=errors,
            )

        prompt = self._build_prompt(tech_events, keyword_docs, cur_start, cur_end)
        raw = self._generate_structured_safe(prompt, TECHNOLOGY_SCHEMA, errors)

        valid_docs = {
            row["document_id"]
            for row in self._store.query_documents_in_range(
                self._topic.id, cur_start, cur_end
            )
        }
        claims, evidences = self._extract_claims(
            raw,
            run_id,
            valid_docs=valid_docs,
            fallback_docs=sorted(valid_docs),
            errors=errors,
        )
        return AnalysisResult(
            ANALYSIS_TECHNOLOGY, cur_start, cur_end, claims=claims,
            evidences=evidences, indices=[thi], errors=errors,
        )

    # ------------------------------------------------------------------ 内部

    def _count_keyword_docs(self, cur_start: str, cur_end: str) -> int:
        """当前窗口内命中技术关键词（topic.keywords.technology）的文档数。"""
        tech_keywords = set(self._topic.keywords.technology)
        if not tech_keywords:
            return 0
        count = 0
        for row in self._store.query_documents_in_range(
            self._topic.id, cur_start, cur_end
        ):
            try:
                matched = set(json.loads(row["matched_keywords"] or "[]"))
            except (ValueError, TypeError):
                matched = set()
            if matched & tech_keywords:
                count += 1
        return count

    def _build_prompt(
        self,
        tech_events: Sequence[object],
        keyword_docs: int,
        cur_start: str,
        cur_end: str,
    ) -> str:
        keywords = ", ".join(self._topic.keywords.technology) or "（无）"
        lines = [
            f"分析窗口：{cur_start} 至 {cur_end}",
            f"\n## 技术关键词（主题定义）：{keywords}",
            f"命中技术关键词的文档数：{keyword_docs}",
            "\n## 本周技术事件",
        ]
        if tech_events:
            for row in tech_events:
                lines.append(
                    f"- [{_row_value(row, 'event_type_id', 'other')}] "
                    f"{_row_value(row, 'title', '')} ({_row_value(row, 'event_date', '')}): "
                    f"{_row_value(row, 'summary', '')}"
                )
        else:
            lines.append("- （无）")
        return "\n".join(lines)
