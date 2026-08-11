"""Risk Signal Analyst：风险分析 + 风险信号指数（RSI）。

RSI 基于风险事件加权计数（严重度权重 × 置信度），确定性计算；
LLM 仅用于把风险事件合成为风险结论（含严重度标注）。
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
    compute_comparison_windows,
)
from industry_intelligence.analysis.models import (
    ANALYSIS_RISK,
    INDEX_RSI,
    AnalysisResult,
    IndexScore,
)

# 风险事件类型 → RSI 严重度权重
RISK_TYPE_WEIGHTS: dict[str, float] = {
    "recall_accident": 4.0,
    "litigation_compliance": 3.0,
    "supply_chain": 2.5,
    "financial_performance": 2.0,
}
RISK_EVENT_TYPES = tuple(RISK_TYPE_WEIGHTS.keys())

#: 负面舆情关键词（用于 prompt 统计）
NEGATIVE_KEYWORDS = ("事故", "召回", "诉讼", "处罚", "亏损", "下滑", "违约")

#: 单个高权重事件 × 10
_RSI_SCALE = 10.0

RISK_SCHEMA = build_claims_schema(
    {"severity": {"type": "string", "enum": ["high", "medium", "low"]}}
)


def compute_rsi(
    events: Sequence[object],
    period_start: str,
    period_end: str,
) -> IndexScore:
    """计算风险信号指数（0-100，确定性）。

    公式：10 × Σ(严重度权重 × 事件置信度)，封顶 100。
    """
    components: dict[str, float] = {}
    total = 0.0
    for row in events:
        etype = str(_row_value(row, "event_type_id", "other"))
        confidence = _as_float_value(_row_value(row, "confidence", 1.0), 1.0)
        weight = RISK_TYPE_WEIGHTS.get(etype, 1.0) * confidence
        components[etype] = components.get(etype, 0.0) + weight
        total += weight
    score = min(100.0, _RSI_SCALE * total)
    return IndexScore(
        index_name=INDEX_RSI,
        entity_id=None,
        score=round(score, 2),
        period_start=period_start,
        period_end=period_end,
        components=components,
    )


class RiskAnalyst(AnalysisAgent):
    """事故 / 召回 / 诉讼 / 合规 / 供应链 / 财务恶化 / 负面舆情。"""

    analysis_type = ANALYSIS_RISK

    def analyze(self, run_id: str) -> AnalysisResult:
        windows = compute_comparison_windows(self._task)
        cur_start, cur_end = windows[WINDOW_CURRENT]
        errors: list[str] = []

        risk_events: list[object] = []
        for etype in RISK_EVENT_TYPES:
            risk_events.extend(
                self._store.query_events_in_range(
                    self._topic.id, cur_start, cur_end, event_type_id=etype
                )
            )
        rsi = compute_rsi(risk_events, cur_start, cur_end)

        if self._provider is None:
            return AnalysisResult(
                ANALYSIS_RISK, cur_start, cur_end, indices=[rsi], errors=errors
            )

        negative_docs = self._count_negative_docs(cur_start, cur_end)
        prompt = self._build_prompt(risk_events, negative_docs, cur_start, cur_end)
        raw = self._generate_structured_safe(prompt, RISK_SCHEMA, errors)

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
            ANALYSIS_RISK, cur_start, cur_end, claims=claims,
            evidences=evidences, indices=[rsi], errors=errors,
        )

    # ------------------------------------------------------------------ 内部

    def _count_negative_docs(self, cur_start: str, cur_end: str) -> int:
        """当前窗口内标题/正文命中负面关键词的文档数。"""
        count = 0
        for row in self._store.query_documents_in_range(
            self._topic.id, cur_start, cur_end
        ):
            title = str(_row_value(row, "title", ""))
            content = str(_row_value(row, "content_text", ""))
            if any(kw in title or kw in content for kw in NEGATIVE_KEYWORDS):
                count += 1
        return count

    def _build_prompt(
        self,
        risk_events: Sequence[object],
        negative_docs: int,
        cur_start: str,
        cur_end: str,
    ) -> str:
        lines = [
            f"分析窗口：{cur_start} 至 {cur_end}",
            f"\n## 负面关键词命中文档数：{negative_docs}（关键词：{', '.join(NEGATIVE_KEYWORDS)}）",
            "\n## 本周风险事件",
        ]
        if risk_events:
            for row in risk_events:
                lines.append(
                    f"- [{_row_value(row, 'event_type_id', 'other')}] "
                    f"{_row_value(row, 'title', '')} ({_row_value(row, 'event_date', '')}): "
                    f"{_row_value(row, 'summary', '')}"
                )
        else:
            lines.append("- （无）")
        return "\n".join(lines)
