"""微信摘要（Phase 4，§20.1）：手机可快速阅读的 6 节压缩文本。

纯文本（不含 Markdown 语法），目标 500-800 字。数据全部来自 ReportDataBundle，
优先取高置信度事实结论、高影响力事件与风险信号。
"""

from __future__ import annotations

from industry_intelligence.analysis.models import CLAIM_TYPE_FACT, CLAIM_TYPE_FORECAST
from industry_intelligence.reporting.builder import ReportDataBundle

# 摘要正文目标字数上限（Server酱单条消息限制内）
_MAX_CHARS = 800


def _to_float(value: object, default: float = 0.0) -> float:
    """把 bundle 里可能为 str/int/float/None 的值安全转成 float。"""
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class DigestFormatter:
    """把 ReportDataBundle 渲染为微信推送摘要文本。"""

    def render(self, bundle: ReportDataBundle, report_path: str = "") -> str:
        lines: list[str] = []
        lines.append(f"【产业竞争情报周报 | {bundle.topic_id}】")
        lines.append(f"周期：{bundle.period_start} ~ {bundle.period_end}")
        lines.append("")

        lines.append("一、本周一句话判断")
        one_liner = self._one_liner(bundle)
        lines.append(one_liner or "暂无明确判断。")
        lines.append("")

        lines.append("二、最重要的 5 件事")
        top5 = self._top5(bundle)
        if top5:
            for i, item in enumerate(top5, 1):
                lines.append(f"{i}. {item}")
        else:
            lines.append("1. 本期无重大事件。")
        lines.append("")

        lines.append("三、企业竞争变化")
        entity_lines = self._entity_changes(bundle)
        if entity_lines:
            lines.extend(entity_lines)
        else:
            lines.append("- 暂无企业动态。")
        lines.append("")

        lines.append("四、关键数据")
        data_lines = self._key_data(bundle)
        if data_lines:
            lines.extend(data_lines)
        else:
            lines.append("- 暂无关键数据。")
        lines.append("")

        lines.append("五、风险/机会")
        risk = self._risk_opportunity(bundle)
        if risk:
            lines.extend(risk)
        else:
            lines.append("- 暂无显著风险或机会。")
        lines.append("")

        lines.append("六、需要继续跟踪")
        watch = self._watch(bundle)
        if watch:
            lines.extend(watch)
        else:
            lines.append("- 暂无。")
        lines.append("")

        quality = self._quality_level(bundle)
        lines.append(f"数据质量：{quality}")
        if report_path:
            lines.append(f"完整报告：{report_path}")
        return self._truncate("\n".join(lines))

    # ------------------------------------------------------------- 各节

    def _one_liner(self, bundle: ReportDataBundle) -> str:
        facts = sorted(
            [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FACT],
            key=lambda c: _to_float(c.get("confidence")),
            reverse=True,
        )
        if facts:
            return str(facts[0].get("claim_text", "")).strip()
        return ""

    def _top5(self, bundle: ReportDataBundle) -> list[str]:
        """按事件日期取最近 5 条，无事件时取高置信度事实结论。"""
        events = sorted(
            bundle.events,
            key=lambda e: str(e.get("event_date", "")),
            reverse=True,
        )
        out = [str(e.get("title", "")) for e in events[:5] if e.get("title")]
        if out:
            return out
        facts = sorted(
            [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FACT],
            key=lambda c: _to_float(c.get("confidence")),
            reverse=True,
        )
        return [str(c.get("claim_text", "")) for c in facts[:5] if c.get("claim_text")]

    def _entity_changes(self, bundle: ReportDataBundle) -> list[str]:
        by_entity: dict[str, list[dict[str, object]]] = {}
        for c in bundle.claims:
            entity = str(c.get("entity_id") or "")
            if entity:
                by_entity.setdefault(entity, []).append(c)
        out: list[str] = []
        for entity, claims in by_entity.items():
            top = claims[0]
            label = "[事实]" if top.get("claim_type") == CLAIM_TYPE_FACT else "[推断]"
            out.append(f"- {entity}：{label} {top.get('claim_text', '')}")
        return out[:5]

    def _key_data(self, bundle: ReportDataBundle) -> list[str]:
        out: list[str] = []
        for o in bundle.observations[:5]:
            out.append(
                f"- {o.get('metric_id', '')}：{o.get('value', '')}{o.get('unit', '')}"
                f"（{o.get('entity_id', '')}）"
            )
        return out

    def _risk_opportunity(self, bundle: ReportDataBundle) -> list[str]:
        risk_claims = [
            c for c in bundle.claims if c.get("analysis_type") == "risk"
        ]
        out: list[str] = []
        for c in risk_claims[:3]:
            out.append(f"- 风险：{c.get('claim_text', '')}")
        forecasts = [
            c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FORECAST
        ]
        for c in forecasts[:2]:
            out.append(f"- 机会：{c.get('claim_text', '')}")
        return out

    def _watch(self, bundle: ReportDataBundle) -> list[str]:
        watch = [
            c for c in bundle.claims
            if c.get("claim_type") == CLAIM_TYPE_FORECAST
            or _to_float(c.get("confidence")) < 0.5
        ]
        return [f"- {c.get('claim_text', '')}" for c in watch[:3]]

    def _quality_level(self, bundle: ReportDataBundle) -> str:
        coverage = float(bundle.quality.get("evidence_coverage", 0.0))
        reject_rate = float(bundle.quality.get("review_reject_rate", 0.0))
        if coverage >= 0.8 and reject_rate <= 0.2:
            return "High"
        if coverage >= 0.5:
            return "Medium"
        return "Low"

    def _truncate(self, text: str, limit: int = _MAX_CHARS) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n…[已截断]"
