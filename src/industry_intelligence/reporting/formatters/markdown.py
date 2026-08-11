"""Markdown 完整周报（Phase 4，§20.2）。

15 节结构，全部数据来自 ReportDataBundle（确定性，不依赖 LLM）。
空数据节显示"本期无此项数据"，不虚构内容。
"""

from __future__ import annotations

from industry_intelligence.analysis.models import (
    CLAIM_TYPE_FACT,
    CLAIM_TYPE_FORECAST,
    CLAIM_TYPE_INFERENCE,
    CLAIM_TYPE_UNKNOWN,
    TREND_INDICATORS,
)
from industry_intelligence.reporting.builder import ReportDataBundle

# claim_type → 结论标签（§20.4）
_CLAIM_LABELS: dict[str, str] = {
    CLAIM_TYPE_FACT: "[事实]",
    CLAIM_TYPE_INFERENCE: "[推断]",
    CLAIM_TYPE_FORECAST: "[预测]",
    CLAIM_TYPE_UNKNOWN: "[数据不足]",
}


def _to_float(value: object, default: float = 0.0) -> float:
    """把 bundle 里可能为 str/int/float/None 的值安全转成 float。"""
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MarkdownFormatter:
    """把 ReportDataBundle 渲染为 15 节 Markdown 周报。"""

    def render(self, bundle: ReportDataBundle) -> str:
        title = (
            f"# 产业竞争情报周报：{bundle.topic_id}\n\n"
            f"- 运行：{bundle.run_id}（状态 {bundle.status}）\n"
            f"- 周期：{bundle.period_start} 至 {bundle.period_end}\n"
        )
        sections = [
            self._executive_summary(bundle),
            self._core_conclusions(bundle),
            self._market_data(bundle),
            self._competitive_landscape(bundle),
            self._company_activity(bundle),
            self._product_technology(bundle),
            self._price_channel(bundle),
            self._policy_regulation(bundle),
            self._investment_m_and_a(bundle),
            self._risk_signals(bundle),
            self._opportunity_assessment(bundle),
            self._trend_comparison(bundle),
            self._watchlist(bundle),
            self._data_integrity(bundle),
            self._sources_evidence(bundle),
        ]
        return title + "\n\n".join(sections) + "\n"

    # ------------------------------------------------------------- 各节

    def _executive_summary(self, bundle: ReportDataBundle) -> str:
        lines = ["## 1. 执行摘要", ""]
        facts = [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FACT]
        top = sorted(facts, key=lambda c: _to_float(c.get("confidence")), reverse=True)[:3]
        if top:
            for c in top:
                label = _CLAIM_LABELS.get(str(c.get("claim_type")), "")
                lines.append(f"- {label} {c.get('claim_text', '')}")
        else:
            lines.append("本期无高置信度事实结论。")
        lines.append("")
        lines.append(
            f"共 {len(bundle.claims)} 条分析结论，{len(bundle.documents)} 篇文档，"
            f"{len(bundle.events)} 个事件，{len(bundle.observations)} 条指标观测。"
        )
        return "\n".join(lines)

    def _core_conclusions(self, bundle: ReportDataBundle) -> str:
        lines = ["## 2. 本周期核心结论", ""]
        claims = sorted(
            bundle.claims,
            key=lambda c: _to_float(c.get("confidence")),
            reverse=True,
        )
        if claims:
            for c in claims[:10]:
                lines.append(self._claim_line(bundle, c))
        else:
            lines.append("本期无分析结论。")
        return "\n".join(lines)

    def _market_data(self, bundle: ReportDataBundle) -> str:
        return self._claims_section("3. 市场关键数据", bundle, "market")

    def _competitive_landscape(self, bundle: ReportDataBundle) -> str:
        return self._claims_section("4. 竞争格局", bundle, "competitor")

    def _company_activity(self, bundle: ReportDataBundle) -> str:
        lines = ["## 5. 重点企业动态", ""]
        by_entity: dict[str, list[dict[str, object]]] = {}
        for c in bundle.claims:
            entity = str(c.get("entity_id") or "（未指定实体）")
            by_entity.setdefault(entity, []).append(c)
        if not by_entity:
            lines.append("本期无企业动态。")
        for entity, claims in by_entity.items():
            lines.append(f"### {entity}")
            for c in claims:
                lines.append(f"- {self._claim_line(bundle, c)}")
        return "\n".join(lines)

    def _product_technology(self, bundle: ReportDataBundle) -> str:
        return self._claims_section("6. 产品与技术", bundle, "technology")

    def _price_channel(self, bundle: ReportDataBundle) -> str:
        lines = ["## 7. 价格与渠道", ""]
        prices = [o for o in bundle.observations if o.get("metric_id") == "price"]
        if prices:
            for o in prices:
                period = (
                    f"{o.get('period_start', '')} ~ {o.get('period_end', '')}"
                )
                lines.append(
                    f"- {o.get('entity_id', '')}：{o.get('value', '')} "
                    f"{o.get('unit', '')}（期间 {period}）"
                )
        else:
            lines.append("本期无价格观测数据。")
        return "\n".join(lines)

    def _policy_regulation(self, bundle: ReportDataBundle) -> str:
        lines = ["## 8. 政策与监管", ""]
        events = [e for e in bundle.events if e.get("event_type_id") == "policy_regulation"]
        if events:
            for e in events:
                lines.append(f"- [{e.get('event_date', '')}] {e.get('title', '')}")
        else:
            lines.append("本期无政策与监管事件。")
        return "\n".join(lines)

    def _investment_m_and_a(self, bundle: ReportDataBundle) -> str:
        lines = ["## 9. 投融资/并购/项目", ""]
        etypes = {"financing", "m_and_a", "investment_expansion", "capacity_build"}
        events = [e for e in bundle.events if e.get("event_type_id") in etypes]
        if events:
            for e in events:
                etype = e.get("event_type_id", "")
                lines.append(
                    f"- [{e.get('event_date', '')}] ({etype}) {e.get('title', '')}"
                )
        else:
            lines.append("本期无投融资/并购/重大项目事件。")
        return "\n".join(lines)

    def _risk_signals(self, bundle: ReportDataBundle) -> str:
        lines = ["## 10. 风险信号", ""]
        risk_claims = [c for c in bundle.claims if c.get("analysis_type") == "risk"]
        if risk_claims:
            for c in risk_claims:
                lines.append(f"- {self._claim_line(bundle, c)}")
        else:
            lines.append("本期无显著风险信号。")
        return "\n".join(lines)

    def _opportunity_assessment(self, bundle: ReportDataBundle) -> str:
        lines = ["## 11. 机会判断", ""]
        forecasts = [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FORECAST]
        if forecasts:
            for c in forecasts:
                lines.append(f"- {self._claim_line(bundle, c)}")
        else:
            lines.append("本期无明确机会判断。")
        return "\n".join(lines)

    def _trend_comparison(self, bundle: ReportDataBundle) -> str:
        lines = ["## 12. 历史趋势比较", ""]
        if not bundle.trends:
            lines.append("本期无历史趋势数据。")
            return "\n".join(lines)
        for name in sorted(TREND_INDICATORS):
            indicators = bundle.trends.get(name, [])
            lines.append(f"### {name}")
            if not indicators:
                lines.append("- 本期无数据")
                continue
            for t in indicators:
                entity = f"（{t.get('entity_id')}）" if t.get("entity_id") else ""
                lines.append(
                    f"- 当前 {t.get('current_value', 0.0)} / 上周 {t.get('previous_value', 0.0)}"
                    f" / 4 周基准 {t.get('baseline_avg', 0.0)}，"
                    f"环比 {t.get('delta_pct', 0.0)}%{entity}"
                )
        return "\n".join(lines)

    def _watchlist(self, bundle: ReportDataBundle) -> str:
        lines = ["## 13. 下周期重点监测清单", ""]
        watch = [
            c for c in bundle.claims
            if c.get("claim_type") == CLAIM_TYPE_FORECAST
            or _to_float(c.get("confidence")) < 0.5
        ]
        if watch:
            for c in watch[:8]:
                lines.append(f"- {self._claim_line(bundle, c)}")
        else:
            lines.append("本期无特别需要继续跟踪的结论。")
        return "\n".join(lines)

    def _data_integrity(self, bundle: ReportDataBundle) -> str:
        lines = ["## 14. 数据完整性说明", ""]
        q = bundle.quality
        lines.append(
            f"- 文档数：{q.get('document_count', 0):.0f}；事件数：{q.get('event_count', 0):.0f}"
        )
        lines.append(
            f"- 指标观测数：{q.get('observation_count', 0):.0f}；"
            f"分析结论数：{q.get('claim_count', 0):.0f}"
        )
        lines.append(f"- 证据覆盖率：{q.get('evidence_coverage', 0.0) * 100:.1f}%")
        lines.append(
            f"- 已审查结论：{q.get('review_count', 0):.0f} 条，"
            f"其中拒绝 {q.get('review_reject_count', 0):.0f} 条"
        )
        if bundle.errors:
            lines.append("- 运行错误：" + "；".join(bundle.errors[:5]))
        return "\n".join(lines)

    def _sources_evidence(self, bundle: ReportDataBundle) -> str:
        lines = ["## 15. 来源与证据附录", ""]
        if bundle.documents:
            lines.append("### 文档清单")
            for d in bundle.documents:
                grade = d.get("source_grade", "")
                lines.append(
                    f"- [{grade}] {d.get('title', '')}（{d.get('source_id', '')}，"
                    f"{d.get('published_at', d.get('fetched_at', ''))}）"
                )
        else:
            lines.append("本期无文档。")
        lines.append("")
        lines.append("### 证据链")
        ev_count = sum(
            1 for c in bundle.claims if isinstance(c.get("evidence"), list) and c["evidence"]
        )
        lines.append(f"共 {len(bundle.claims)} 条结论，其中 {ev_count} 条挂接证据。")
        return "\n".join(lines)

    # ------------------------------------------------------------- 助手

    def _claims_section(
        self, heading: str, bundle: ReportDataBundle, analysis_type: str
    ) -> str:
        lines = [f"## {heading}", ""]
        claims = [c for c in bundle.claims if c.get("analysis_type") == analysis_type]
        if claims:
            for c in claims:
                lines.append(f"- {self._claim_line(bundle, c)}")
        else:
            lines.append("本期无此项数据。")
        return "\n".join(lines)

    def _claim_line(
        self, bundle: ReportDataBundle, claim: dict[str, object]
    ) -> str:
        label = _CLAIM_LABELS.get(str(claim.get("claim_type")), "[数据不足]")
        evidence = claim.get("evidence")
        ev_ref = ""
        if isinstance(evidence, list) and evidence:
            doc_ids = [e.get("document_id") for e in evidence if e.get("document_id")]
            ev_ref = f" 证据：{', '.join(str(d) for d in doc_ids[:3])}"
        review = self._review_for(bundle, str(claim.get("claim_id", "")))
        review_note = ""
        if review:
            verdict = review.get("verdict")
            if verdict == "reject":
                review_note = " [审查：拒绝]"
            elif verdict == "downgrade":
                review_note = f" [审查：已降级 → {review.get('downgrade_to')}]"
            elif verdict == "pass":
                review_note = " [审查：通过]"
        return f"{label} {claim.get('claim_text', '')}{review_note}{ev_ref}"

    def _review_for(
        self, bundle: ReportDataBundle, claim_id: str
    ) -> dict[str, object] | None:
        for r in bundle.review_results:
            if str(r.get("claim_id", "")) == claim_id:
                return r
        return None
