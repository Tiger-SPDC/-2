"""推送早报提炼：把「最重要的几件事」从标题升维成早报式一句话。

用户需求（v0.7.0a10）：推送不能只给标题；每条要像早报一样讲清「发生了什么」。
实现：对选中的 top 事件，尽量取到正文（bundle 已有正文回填，缺失时回访原文），
交给 LLM 提炼成简洁中文早报。无正文 / 无 provider / LLM 失败一律降级返回空，
由 formatter 回退用原标题——绝不虚构、绝不中断。
"""

from __future__ import annotations

from typing import Any

from industry_intelligence.llm.provider import LLMError, LLMProvider

# 单条早报目标字数上限（中文，含标点）
_BRIEFING_MAX = 60
# 每条事件喂给 LLM 的正文上限（避免超长溢出 token）
_BODY_MAX = 800

# LLM 结构化输出 schema：每条标题 + 一条早报
BRIEFING_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "事件原标题（用于对齐）"},
                    "briefing": {
                        "type": "string",
                        "description": "一条简洁中文早报：讲清谁做了什么/影响/数据",
                    },
                },
                "required": ["title", "briefing"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_DEFAULT_TEMPLATE = (
    "你是一名产业情报早报编辑。请阅读下面每条新闻的标题与正文，把它们提炼成"
    "一条简洁的中文早报，让人不看原文就明白发生了什么。"
    "只返回 JSON：{\"items\": [{\"title\": \"原标题\", \"briefing\": \"提炼句\"}]}。"
    "要求：briefing 一句话（最多两句、不超过 {max_len} 字）；讲清核心事实"
    "（谁/做了什么/影响或数据）；语言完整通顺、不含空话套话；"
    "不要照抄原标题，不要臆测正文没有的信息。"
)


def pick_top_events(bundle: Any, limit: int = 5) -> list[dict[str, object]]:
    """筛选+排序 top 事件，返回事件 dict 列表（按标题去重）。

    - 过滤：命中 core 且不命中 exclude（_filter_events，与 formatter 一致）。
    - 排序：日期倒序，命中热点优先。
    - 去重：同一新闻被多个来源聚成不同事件（标题相似度仅差来源后缀）时，只保留
      一条，避免早报里出现重复内容。用归一化标题（去掉 ` - 来源` 尾巴）相互比较。

    保证「选出谁」与「推送谁」一致，且同新闻不重复上屏。
    """
    from industry_intelligence.reporting.formatters.digest import _filter_events

    hot = [str(t).strip() for t in bundle.hot_topics if str(t).strip()]
    events = _filter_events(bundle.events, bundle.focus_terms, bundle.exclude_terms)
    events = sorted(
        events, key=lambda e: str(e.get("event_date", "")), reverse=True
    )
    if hot:
        events.sort(
            key=lambda e: _matches_hot(e, hot),
        )
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for e in events:
        key = _norm_title(str(e.get("title") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped[:limit]


def _norm_title(title: str) -> str:
    """归一化标题用于去重：去掉 ` - 来源` 尾巴，压缩空白。

    同一新闻被多个来源转载时，标题差异只在来源后缀（如「… - 新浪财经」vs
    「… - 驱动之家」），去掉后有相同核身，可避免同新闻重复上屏。
    """
    text = title.strip()
    if " - " in text:
        text = text.rsplit(" - ", 1)[0].strip()
    return " ".join(text.split())


def _matches_hot(event: dict[str, object], hot: list[str]) -> int:
    """排序权重：命中热点排前（0），否则 1。"""
    from industry_intelligence.reporting.formatters.digest import _matches_any

    text = " ".join(str(event.get(k, "")) for k in ("title", "summary"))
    return 0 if _matches_any(text, hot) else 1


def fetch_event_bodies(bundle: Any) -> dict[str, list[dict[str, object]]]:
    """从 bundle.event_body 回填正文；对正文缺失/过短的（RSS 链接页）回访原文。

    返回 {event_id: [{"title", "url", "content_text"}]}。回访失败不抛——跳过该事件
    的正文，让 BriefingGenerator 只对能拿到正文的事件做提炼。
    """
    bodies: dict[str, list[dict[str, object]]] = {}
    get_uril = getattr(bundle, "event_body", None) or {}
    for event_id, docs in get_uril.items():
        if not isinstance(docs, list):
            continue
        filled: list[dict[str, object]] = []
        for d in docs:
            if not isinstance(d, dict):
                continue
            url = str(d.get("canonical_url") or d.get("url") or "")
            text = str(d.get("content_text") or "").strip()
            # 正文过短（RSS 的链接 HTML 或空）→ 尝试回访原文
            if len(text) < 50 and url:
                fetched = _fetch_and_extract(url)
                if fetched:
                    text = fetched
            if text:
                filled.append(
                    {
                        "title": str(d.get("title") or ""),
                        "url": url,
                        "content_text": text,
                    }
                )
        if filled:
            bodies[event_id] = filled
    return bodies


def _fetch_and_extract(url: str) -> str:
    """回访一篇文章正文（HTML 标签剥离）；失败返回空串。"""
    try:
        from industry_intelligence.sources.html_adapter import _extract_html
        from industry_intelligence.utils.http import fetch_text

        raw = fetch_text(url, timeout=15)
        if not raw:
            return ""
        _, text = _extract_html(raw)
        return text.strip()
    except Exception:  # noqa: BLE001 — 回访失败不影响整体，降级跳过
        return ""


class BriefingGenerator:
    """用 LLM 把 top 事件提炼成早报式一句话。

    无 provider / LLM 失败 / 读不到正文 → 返回空 dict；调用方回退用原标题。
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        prompt_template: str = "",
        max_len: int = _BRIEFING_MAX,
    ) -> None:
        self._provider = provider
        self._template = prompt_template or _DEFAULT_TEMPLATE
        self._template = self._template.replace("{max_len}", str(max_len))
        self._max_len = max_len

    def generate(
        self, events: list[dict[str, object]], event_bodies: dict[str, list[dict[str, object]]]
    ) -> dict[str, str]:
        """返回 {event_id: 早报句}；无 provider / 失败 / 无正文返回空 dict。"""
        if self._provider is None or not events:
            return {}
        prompt = self._build_prompt(events, event_bodies)
        if not prompt:
            return {}
        try:
            raw = self._provider.generate_structured(prompt, BRIEFING_SCHEMA)
        except LLMError:
            return {}
        return _parse_briefings(raw, events, self._max_len)

    def _build_prompt(
        self,
        events: list[dict[str, object]],
        event_bodies: dict[str, list[dict[str, object]]],
    ) -> str:
        lines = [self._template, ""]
        any_body = False
        for ev in events:
            eid = str(ev.get("event_id") or "")
            title = str(ev.get("title") or "")
            body = _join_body(event_bodies.get(eid))
            if not title:
                continue
            if body:
                any_body = True
                lines.append(f"标题：{title}\n正文：{body[:_BODY_MAX]}")
            else:
                # 无正文：只给标题，让 LLM 基于标题谨慎推测，不硬编
                lines.append(f"标题：{title}\n正文：（未采集到正文）")
            lines.append("---")
        return "\n".join(lines) if any_body else ""


def _join_body(docs: list[dict[str, object]] | None) -> str:
    """把一事件关联文档的正文拼接（去重、截断）。"""
    if not docs:
        return ""
    seen: set[str] = set()
    parts: list[str] = []
    for d in docs:
        text = str(d.get("content_text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return "\n".join(parts)[:_BODY_MAX]


def _parse_briefings(
    raw: dict[str, object], events: list[dict[str, object]], max_len: int
) -> dict[str, str]:
    """容错解析 LLM 返回：按 title 对齐回 event_id；截断到 max_len；剔除空串。"""
    items = raw.get("items")
    if not isinstance(items, list):
        return {}
    by_title: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        briefing = str(item.get("briefing") or "").strip()
        if title and briefing:
            by_title[title] = briefing
    out: dict[str, str] = {}
    for ev in events:
        title = str(ev.get("title") or "").strip()
        text = by_title.get(title)
        if text:
            out[str(ev.get("event_id") or "")] = _truncate_cn(text, max_len)
    return out


def _truncate_cn(text: str, max_len: int) -> str:
    """早报中文截断：优先截到句末标点，不切半句；无标点才硬截加省略号。"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    head = text[:max_len]
    for i in range(len(head) - 1, -1, -1):
        if head[i] in "。！？；!?;":
            return head[: i + 1].rstrip()
    return head[: max_len - 1].rstrip() + "…"
