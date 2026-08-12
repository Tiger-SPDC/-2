"""微信摘要（Phase 4，§20.1）：手机可快速阅读的 3 节压缩文本。

纯文本（不含 Markdown 语法），总字数（含标点）≤600。结构：
一、本周一句话判断；二、最重要的 5 件事（行业相关）；三、企业竞争变化（企业相关）。
数据全部来自 ReportDataBundle。超长时只截正文，数据质量等级与完整报告链接始终保留。
"""

from __future__ import annotations

from industry_intelligence.analysis.models import CLAIM_TYPE_FACT
from industry_intelligence.reporting.builder import ReportDataBundle

# 摘要总字数上限（Server酱单条消息限制内，含标点）
_MAX_CHARS = 600


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
        parts: list[str] = []
        parts.append(f"【产业竞争情报周报 | {bundle.topic_id}】")
        parts.append(f"周期：{bundle.period_start} ~ {bundle.period_end}")
        parts.append("")

        parts.append("一、本周一句话判断")
        parts.append(self._one_liner(bundle) or "暂无明确判断。")
        parts.append("")

        parts.append("二、最重要的 5 件事")
        top5 = self._top5(bundle)
        if top5:
            parts.extend(f"{i}. {item}" for i, item in enumerate(top5, 1))
        else:
            parts.append("1. 本期无重大事件。")
        parts.append("")

        parts.append("三、企业竞争变化")
        entity_lines = self._entity_changes(bundle)
        if entity_lines:
            parts.extend(entity_lines)
        else:
            parts.append("- 暂无企业动态。")

        body = "\n".join(parts)
        footer = f"\n数据质量：{self._quality_level(bundle)}"
        if report_path:
            footer += f"\n完整报告：{report_path}"
        return self._fit(body, footer)

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

    def _quality_level(self, bundle: ReportDataBundle) -> str:
        coverage = float(bundle.quality.get("evidence_coverage", 0.0))
        reject_rate = float(bundle.quality.get("review_reject_rate", 0.0))
        if coverage >= 0.8 and reject_rate <= 0.2:
            return "High"
        if coverage >= 0.5:
            return "Medium"
        return "Low"

    def _fit(self, body: str, footer: str, limit: int = _MAX_CHARS) -> str:
        """正文超长时只截正文，质量等级与完整报告链接始终保留。"""
        if len(body) + len(footer) <= limit:
            return body + footer
        marker = "\n…[已截断]"
        budget = limit - len(footer) - len(marker)
        if budget <= 0:
            return (body + footer)[:limit]
        return body[:budget].rstrip() + marker + footer
