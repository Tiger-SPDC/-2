"""Market Analyst：市场分析 + 市场动量指数（MMI）。

MMI 基于当前 vs 前窗口的可量化观测值变化率（按指标加权），确定性计算；
LLM 仅用于把事件计数与观测数据合成为市场结论（含排名证据级别标注）。
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
    ANALYSIS_MARKET,
    INDEX_MMI,
    AnalysisResult,
    IndexScore,
)

# 指标 → MMI 权重（市场销量/份额权重最高，价格权重低）
MARKET_METRIC_WEIGHTS: dict[str, float] = {
    "market_sales": 3.0,
    "market_share": 2.5,
    "price": 1.0,
}

# 市场相关事件类型（用于 prompt 计数）
MARKET_EVENT_TYPES = (
    "policy_regulation",
    "bid_order",
    "channel_expansion",
    "financing",
    "market_sales",
)

MARKET_SCHEMA = build_claims_schema()


def _group_avg(rows: Sequence[object]) -> dict[str, float]:
    """按 metric_id 分组，返回各指标的观测平均值。"""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in rows:
        metric = str(_row_value(row, "metric_id", ""))
        raw = _row_value(row, "value", None)
        if not metric or isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        sums[metric] = sums.get(metric, 0.0) + float(raw)
        counts[metric] = counts.get(metric, 0) + 1
    return {m: sums[m] / counts[m] for m in sums}


def compute_mmi(
    current_obs: Sequence[object],
    previous_obs: Sequence[object],
    period_start: str,
    period_end: str,
) -> IndexScore:
    """计算市场动量指数（0-100，确定性，主题级）。

    公式：100 × Σ(指标权重 × max(0, 当前均值 - 前窗口均值)/前窗口均值)，封顶 100。
    前窗口无数据或无变化时贡献为 0。components 记录各指标贡献。
    """
    current = _group_avg(current_obs)
    previous = _group_avg(previous_obs)
    components: dict[str, float] = {}
    total = 0.0
    for metric in set(current) | set(previous):
        weight = MARKET_METRIC_WEIGHTS.get(metric, 1.0)
        cur_v = current.get(metric)
        prev_v = previous.get(metric)
        if cur_v is None or prev_v is None or prev_v == 0:
            growth = 0.0
        else:
            growth = (cur_v - prev_v) / prev_v
        # components 记录原始贡献（可为负，便于审计）；得分只取正向动量
        components[metric] = round(weight * growth, 4)
        total += weight * max(0.0, growth)
    score = min(100.0, total * 100.0)
    return IndexScore(
        index_name=INDEX_MMI,
        entity_id=None,
        score=round(score, 2),
        period_start=period_start,
        period_end=period_end,
        components=components,
    )


class MarketAnalyst(AnalysisAgent):
    """市场规模 / 排名（R1 官方 / R2 重算 / R3 活动度）/ 地区 / 渠道 / 价格 / 需求 / 政策。"""

    analysis_type = ANALYSIS_MARKET

    def analyze(self, run_id: str) -> AnalysisResult:
        windows = compute_comparison_windows(self._task)
        cur_start, cur_end = windows[WINDOW_CURRENT]
        last_start, last_end = windows[WINDOW_LAST]
        errors: list[str] = []

        current_obs = self._store.query_observations_in_range(
            self._topic.id, start_date=cur_start, end_date=cur_end
        )
        previous_obs = self._store.query_observations_in_range(
            self._topic.id, start_date=last_start, end_date=last_end
        )
        mmi = compute_mmi(current_obs, previous_obs, cur_start, cur_end)

        if self._provider is None:
            return AnalysisResult(
                ANALYSIS_MARKET, cur_start, cur_end, indices=[mmi], errors=errors
            )

        counts = self._store.count_events_by_type(
            self._topic.id, start_date=cur_start, end_date=cur_end
        )
        prompt = self._build_prompt(counts, current_obs, cur_start, cur_end)
        raw = self._generate_structured_safe(prompt, MARKET_SCHEMA, errors)

        valid_docs = {
            row["document_id"]
            for row in self._store.query_documents_in_range(
                self._topic.id, cur_start, cur_end
            )
        }
        valid_obs = {row["observation_id"] for row in current_obs}

        claims, evidences = self._extract_claims(
            raw,
            run_id,
            valid_docs=valid_docs,
            valid_obs=valid_obs,
            fallback_docs=sorted(valid_docs),
            errors=errors,
        )
        return AnalysisResult(
            ANALYSIS_MARKET, cur_start, cur_end, claims=claims,
            evidences=evidences, indices=[mmi], errors=errors,
        )

    # ------------------------------------------------------------------ 内部

    def _build_prompt(
        self,
        counts: dict[str, int],
        observations: Sequence[object],
        cur_start: str,
        cur_end: str,
    ) -> str:
        lines = [f"分析窗口：{cur_start} 至 {cur_end}", "\n## 本周事件类型计数"]
        if counts:
            lines.extend(f"- {k}: {v}" for k, v in sorted(counts.items()))
        else:
            lines.append("- （无）")
        lines.append("\n## 本周量化观测值")
        if observations:
            for row in observations:
                lines.append(
                    f"- [{_row_value(row, 'metric_id', '')}] "
                    f"{_row_value(row, 'entity_id', '')}: "
                    f"{_as_float_value(_row_value(row, 'value', 0), 0.0)}"
                    f"{_row_value(row, 'unit', '')}"
                )
        else:
            lines.append("- （无）")
        return "\n".join(lines)
