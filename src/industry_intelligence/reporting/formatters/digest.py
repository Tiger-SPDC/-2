"""微信摘要（Phase 4，§20.1）：手机可快速阅读的 3 节压缩文本。

纯文本（不含 Markdown 语法），总字数（含标点）≤600。结构：
一、本周一句话判断；二、最重要的 5 件事（行业相关）；三、企业竞争变化（企业相关）。
数据全部来自 ReportDataBundle。超长时只截正文，数据质量等级与完整报告链接始终保留。
v0.7.0a6：顶部新增"本期热点关注"行（LLM 动态热点）；5 件事优先排命中热点的
事件；企业节内容优先——有实际动态的企业先列，无动态不再占用位置。
"""

from __future__ import annotations

from industry_intelligence.analysis.models import CLAIM_TYPE_FACT
from industry_intelligence.reporting.builder import ReportDataBundle

# 摘要总字数上限（Server酱单条消息限制内，含标点）
_MAX_CHARS = 600

# 企业节最小条数：有动态的企业不足此数时才用跟踪企业"暂无动态"补足
_MIN_ENTITY_LINES = 3

# 各节条数上限与最小保留条数：整体超长时"减条数"（5→4→3），而非截断单条
_MAX_ITEMS = 5
_MIN_TOP_ITEMS = 3  # 5 件事最少保留条数

# 各节"单条"字数上限：仅当单条极长时才语义截断（截到句号，不硬切半句）。
# 上限取宽松值，保证正常完整句子（企业动态/标题通常 ≤60~80 字）不被截；
# 整体超长时靠"减条数"（5→4→3）适配，而非截断单条。
_ONE_LINER_MAX = 60  # 一句话判断（应保持精炼）
_TOP5_TITLE_MAX = 50  # 5 件事每条标题
_ENTITY_TEXT_MAX = 90  # 企业节每条动态文案（不含实体名与标签）

# 语义截断的句子结束符（优先截到这里，避免话说一半）
_SENTENCE_END = "。！？；!?;"


def _to_float(value: object, default: float = 0.0) -> float:
    """把 bundle 里可能为 str/int/float/None 的值安全转成 float。"""
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: object | None) -> list[object]:
    """把 bundle 里可能为 list/None 的字段安全转成 list（mypy 友好）。"""
    if not isinstance(value, list):
        return []
    return value


def _truncate(text: str, max_len: int) -> str:
    """语义截断：超长时优先截到句子结束符（。！？；），避免"话说一半"。

    若 max_len 内存在较靠后的句子边界，截到该处（完整句子，不加省略号）；
    否则硬截并加省略号。结果 ≤ max_len。
    """
    text = text.strip()
    if len(text) <= max_len:
        return text
    head = text[:max_len]
    idx = -1
    for i in range(len(head) - 1, -1, -1):
        if head[i] in _SENTENCE_END:
            idx = i
            break
    # 句子边界不能太靠前（否则只剩半句），阈值取一半
    if idx >= max_len // 2:
        return text[: idx + 1].rstrip()
    return head.rstrip()[: max_len - 1] + "…"


class DigestFormatter:
    """把 ReportDataBundle 渲染为微信推送摘要文本。"""

    def render(self, bundle: ReportDataBundle, report_path: str = "") -> str:
        hot_line = self._hot_topics_line(bundle)
        one_liner = self._one_liner(bundle) or "暂无明确判断。"
        top5 = self._top5(bundle)
        entity_lines = self._entity_changes(bundle)
        footer = f"\n数据质量：{self._quality_level(bundle)}"
        if report_path:
            footer += f"\n完整报告：{report_path}"
        return self._fit_sections(
            bundle, hot_line, one_liner, top5, entity_lines, footer
        )

    # ------------------------------------------------------------- 组装

    def _build_body(
        self,
        bundle: ReportDataBundle,
        hot_line: str,
        one_liner: str,
        top5: list[str],
        entity_lines: list[str],
    ) -> str:
        """按给定条数组装正文（条数由 _fit_sections 决定，此处不截断）。"""
        parts: list[str] = []
        parts.append(f"【产业竞争情报周报 | {bundle.topic_id}】")
        parts.append(f"周期：{bundle.period_start} ~ {bundle.period_end}")
        if hot_line:
            parts.append("")
            parts.append(hot_line)
        parts.append("")
        parts.append("一、本周一句话判断")
        parts.append(one_liner)
        parts.append("")
        parts.append(f"二、最重要的 {len(top5) or 1} 件事")
        if top5:
            parts.extend(f"{i}. {item}" for i, item in enumerate(top5, 1))
        else:
            parts.append("1. 本期无重大事件。")
        parts.append("")
        parts.append("三、企业竞争变化")
        if entity_lines:
            parts.extend(entity_lines)
        else:
            parts.append("- 暂无企业动态。")
        return "\n".join(parts)

    def _fit_sections(
        self,
        bundle: ReportDataBundle,
        hot_line: str,
        one_liner: str,
        top5: list[str],
        entity_lines: list[str],
        footer: str,
    ) -> str:
        """组装正文：整体超预算时优先减条数（5→4→3），而非截断单条。

        顺序为先 5 件事、后企业节都从多到少尝试，找到首个 ≤600 的组合；
        仍超时才由 _fit 兜底截正文。
        """
        budget = _MAX_CHARS - len(footer)
        top_opts = (
            list(range(min(_MAX_ITEMS, len(top5)), _MIN_TOP_ITEMS - 1, -1))
            or [len(top5)]
        )
        ent_opts = (
            list(range(min(_MAX_ITEMS, len(entity_lines)), _MIN_ENTITY_LINES - 1, -1))
            or [len(entity_lines)]
        )
        for n_top in top_opts:
            for n_ent in ent_opts:
                body = self._build_body(
                    bundle, hot_line, one_liner, top5[:n_top], entity_lines[:n_ent]
                )
                if len(body) <= budget:
                    return body + footer
        body = self._build_body(
            bundle, hot_line, one_liner, top5[:3], entity_lines[:3]
        )
        return self._fit(body, footer)

    # ------------------------------------------------------------- 各节

    def _one_liner(self, bundle: ReportDataBundle) -> str:
        facts = sorted(
            [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FACT],
            key=lambda c: _to_float(c.get("confidence")),
            reverse=True,
        )
        if facts:
            return _truncate(str(facts[0].get("claim_text", "")), _ONE_LINER_MAX)
        return ""

    def _top5(self, bundle: ReportDataBundle) -> list[str]:
        """按事件日期取最近 5 条，命中本期热点的事件优先；无事件时取高置信度事实。

        v0.7.0a6：当次 LLM 热点短语若出现在事件标题/摘要中，该事件排在更前面，
        让推送真正反映热点内容；热点为空时行为与之前完全一致（按日期倒序）。
        """
        hot = [str(t).strip() for t in bundle.hot_topics if str(t).strip()]
        events = sorted(
            bundle.events,
            key=lambda e: str(e.get("event_date", "")),
            reverse=True,
        )
        if hot:
            events.sort(
                key=lambda e: 0 if self._matches_hot(e, hot) else 1
            )  # 稳定排序：命中热点的事件排前，组内仍按日期倒序
        out = [
            _truncate(str(e.get("title", "")), _TOP5_TITLE_MAX)
            for e in events[:5]
            if e.get("title")
        ]
        if out:
            return out
        facts = sorted(
            [c for c in bundle.claims if c.get("claim_type") == CLAIM_TYPE_FACT],
            key=lambda c: _to_float(c.get("confidence")),
            reverse=True,
        )
        return [
            _truncate(str(c.get("claim_text", "")), _TOP5_TITLE_MAX)
            for c in facts[:5]
            if c.get("claim_text")
        ]

    def _matches_hot(self, event: dict[str, object], hot: list[str]) -> bool:
        """事件标题/摘要是否命中任一热点短语（casefold 子串匹配）。"""
        text = " ".join(
            str(event.get(k, "")) for k in ("title", "summary")
        ).casefold()
        return any(h.casefold() in text for h in hot)

    def _hot_topics_line(self, bundle: ReportDataBundle) -> str:
        """本期热点关注行：展示最多 3 条 LLM 动态热点，超长截断保字数。"""
        topics = [str(t).strip() for t in bundle.hot_topics if str(t).strip()]
        if not topics:
            return ""
        shown = "、".join(topics[:3])
        if len(topics) > 3:
            shown += "…"
        if len(shown) > 42:
            shown = shown[:42].rstrip("、") + "…"
        return f"本期热点关注：{shown}"

    def _entity_changes(self, bundle: ReportDataBundle) -> list[str]:
        """企业竞争变化：内容优先，任何有实际动态的企业（含非跟踪）都上屏。

        候选实体 = 跟踪企业 + 主张中出现的企业 + 事件中出现的企业（去重、跟踪优先）。
        先列有实际动态的（最多 5 条）；有动态的不足 _MIN_ENTITY_LINES 条时才用
        跟踪企业的"本期暂无动态"补足到 _MIN_ENTITY_LINES 条——避免空节，
        但不让无内容企业占用有内容企业的位置。
        """
        claim_by_entity: dict[str, list[dict[str, object]]] = {}
        for c in bundle.claims:
            entity = str(c.get("entity_id") or "")
            if entity:
                claim_by_entity.setdefault(entity, []).append(c)
        event_by_entity: dict[str, list[dict[str, object]]] = {}
        for ev in bundle.events:
            for eid in _as_list(ev.get("entity_ids")):
                eid = str(eid)
                if eid:
                    event_by_entity.setdefault(eid, []).append(ev)
        tracked = [str(c["name"]) for c in bundle.companies if c.get("name")]
        # 候选实体：跟踪企业优先，其次主张/事件中出现的企业（去重保序）
        candidates: list[str] = []
        for entity in tracked + list(claim_by_entity) + list(event_by_entity):
            if entity and entity not in candidates:
                candidates.append(entity)
        out: list[str] = []
        # 1) 有实际动态的实体（跟踪优先，其次数据中出现的企业）
        for entity in candidates:
            if len(out) >= 5:
                break
            text = self._entity_activity(entity, claim_by_entity, event_by_entity)
            if text:
                out.append(f"- {entity}：{text}")
        # 2) 有动态的不足 _MIN_ENTITY_LINES 条时，用跟踪企业"本期暂无动态"补足
        if len(out) < _MIN_ENTITY_LINES:
            for entity in tracked:
                if len(out) >= _MIN_ENTITY_LINES:
                    break
                if not self._entity_activity(entity, claim_by_entity, event_by_entity):
                    out.append(f"- {entity}：本期暂无动态")
        return out[:5]

    def _entity_activity(
        self,
        entity: str,
        claim_by_entity: dict[str, list[dict[str, object]]],
        event_by_entity: dict[str, list[dict[str, object]]],
    ) -> str:
        """实体的动态文案：优先分析主张，其次最新事件标题。"""
        claims = claim_by_entity.get(entity)
        if claims:
            top = claims[0]
            label = "[事实]" if top.get("claim_type") == CLAIM_TYPE_FACT else "[推断]"
            return f"{label} {_truncate(str(top.get('claim_text', '')), _ENTITY_TEXT_MAX)}"
        events = event_by_entity.get(entity)
        if events:
            title = str(events[0].get("title") or "").strip()
            if title:
                return f"[事件] {_truncate(title, _ENTITY_TEXT_MAX)}"
        return ""

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
