"""企业竞争变化节：完全动态发现企业 + 关联度排序（去固定种子）。

用户需求（v0.7.0a11）：企业节不该被固定名单（特来电/国家电网等）框住——要动态发现
「这段新闻里被报道/采访/讨论的企业」，按关联度排序。固定名单限制思考、观感局限。

实现：三个来源合并成候选池，去重后做确定性打分，取 top 5：
1. `claims.entity_id`（LLM 分析时自由标注的企业，含非种子——唯一可靠的既有动态来源）
2. `events.entity_ids`（事件关联企业，种子为主，兜底）
3. **LLM 从本段命中的新闻标题/正文提取的企业**（CompanyDiscoverer，能看到非种子企业）

关联度 = 活跃度×出现次数 + 内容相关度×命中大目标词 + 新鲜度×日期近 + 信息量×claim有证据。
排序是确定性、可解释、可调权重；发现是动态的（LLM）。无 provider / LLM 失败降级只用既有来源。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from industry_intelligence.analysis.models import CLAIM_TYPE_FACT
from industry_intelligence.llm.provider import LLMError, LLMProvider

# 企业节上屏上限
_MAX_COMPANIES = 5
# 每条给 LLM 的正文上限（避免超长溢出 token）
_BODY_MAX = 600

# 关联度权重（可按主题调整；和为 1.0 便于解释）
_W_ACTIVE = 0.4   # 活跃度：出现次数
_W_FOCUS = 0.3    # 内容相关度：命中大目标 core / 热点词
_W_FRESH = 0.2    # 新鲜度：事件日期近
_W_INFO = 0.1     # 信息量：claim 有证据/置信度

# LLM 提取企业 schema：从新闻里列出被报道/讨论的企业名
COMPANY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "companies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "这段新闻里被报道/采访/讨论的企业名（不限种子）",
        }
    },
    "required": ["companies"],
    "additionalProperties": False,
}

_DEFAULT_TEMPLATE = (
    "你是产业情报分析。请从下面的新闻标题与正文里，提炼出这段新闻中"
    "「被报道、被采访、被讨论、被引用」的企业/公司（不限是否知名，也不限任何名单）。"
    "只返回 JSON：{\"companies\": [\"企业名1\", \"企业名2\", ...]}。"
    "要求：给企业常见简称（如'小鹏汽车'给'小鹏'）；每条新闻独立判断；"
    "只列真的作为主体被报道或讨论的企业，不要列泛泛提到的公司，不要空串。"
)


def _norm_company(name: str) -> str:
    """归一化企业名用于去重：去 ` - 来源` 尾巴、去掉括号备注、压缩空白。"""
    text = (name or "").strip()
    if " - " in text:
        text = text.rsplit(" - ", 1)[0].strip()
    if "（" in text:
        text = text.split("（", 1)[0].strip()
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    return " ".join(text.split())


def _matches_any(text: str, terms: list[str]) -> bool:
    """text 是否命中 terms 任一（casefold 子串，忽略空词）。"""
    haystack = (text or "").casefold()
    return any(t.casefold() in haystack for t in terms if t)


class CompanyDiscoverer:
    """用 LLM 从本段新闻里提取被报道的企业（不加固定名单）。

    无 provider / LLM 失败 → 返回空列表，由 discover_companies 降级用既有来源。
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        prompt_template: str = "",
    ) -> None:
        self._provider = provider
        self._template = prompt_template or _DEFAULT_TEMPLATE

    def discover(
        self, events: list[dict[str, object]], event_bodies: dict[str, list[dict[str, object]]]
    ) -> list[str]:
        """从事件标题+正文提取企业名列表；失败返回空。"""
        if self._provider is None or not events:
            return []
        prompt = self._build_prompt(events, event_bodies)
        if not prompt:
            return []
        try:
            raw = self._provider.generate_structured(prompt, COMPANY_SCHEMA)
        except LLMError:
            return []
        return _parse_companies(raw)

    def _build_prompt(
        self,
        events: list[dict[str, object]],
        event_bodies: dict[str, list[dict[str, object]]],
    ) -> str:
        lines = [self._template, ""]
        any_body = False
        for ev in events[:15]:  # 只取前面若干条，控制长度
            title = str(ev.get("title") or "")
            body = _join_body(event_bodies.get(str(ev.get("event_id") or "")))
            if not title:
                continue
            if body:
                any_body = True
                lines.append(f"标题：{title}")
                lines.append(f"正文：{body[:_BODY_MAX]}")
            else:
                lines.append(f"标题：{title}")
                lines.append("正文：（未采集到正文）")
            lines.append("---")
        return "\n".join(lines) if any_body else ""


def _join_body(docs: list[dict[str, object]] | None) -> str:
    """把一事件关联文档正文拼接（去重、截断）。"""
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


def _parse_companies(raw: dict[str, object]) -> list[str]:
    """容错解析 LLM 返回：非 list / 非字符串 / 空串 / 重复丢弃。"""
    items = raw.get("companies")
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        name = _norm_company(item)
        if name and name not in out:
            out.append(name)
    return out


class CompanyScorer:
    """确定性关联度打分：把动态候选企业按关联度排序，取 top N。"""

    def __init__(
        self,
        focus_terms: list[str] | None = None,
        hot_topics: list[str] | None = None,
    ) -> None:
        self._focus = [t for t in (focus_terms or []) if t]
        self._hot = [t for t in (hot_topics or []) if t]

    def score_entities(
        self,
        entities: list[str],
        claims: list[dict[str, object]],
        events: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """返回 [{"name":..., "score":float, "claim_count":int, "event_count":int},...] 降序。

        活跃度 = 该企业在 claim 中出现次数 + 在 event.entity_ids 出现次数。
        内容相关度 = 该企业相关 claim 命中 core/热点 的比例。
        新鲜度 = 其相关事件日期越近越高（0~1）。
        信息量 = 相关 claim 有证据的比例。
        """
        # 先给候选建索引
        claim_by: dict[str, list[dict[str, object]]] = {e: [] for e in entities}
        event_by: dict[str, list[dict[str, object]]] = {e: [] for e in entities}
        canonical_index: dict[str, list[str]] = {}
        for e in entities:
            canonical_index.setdefault(_norm_company(e).casefold(), []).append(e)
        for c in claims:
            eid = _norm_company(str(c.get("entity_id") or "")).casefold()
            if eid in canonical_index:
                for name in canonical_index[eid]:
                    claim_by.setdefault(name, []).append(c)
        for ev in events:
            for eid_obj in _as_list(ev.get("entity_ids")):
                norm = _norm_company(str(eid_obj)).casefold()
                if norm in canonical_index:
                    for name in canonical_index[norm]:
                        event_by.setdefault(name, []).append(ev)

        scored: list[dict[str, object]] = []
        for e in entities:
            cl = claim_by.get(e, [])
            evs = event_by.get(e, [])
            score = self._score(e, cl, evs)
            if score <= 0:
                continue
            scored.append(
                {
                    "name": e,
                    "score": round(score, 4),
                    "claim_count": len(cl),
                    "event_count": len(evs),
                }
            )
        scored.sort(key=lambda d: float(str(d["score"])), reverse=True)
        return scored[:_MAX_COMPANIES]

    def _score(
        self, entity: str, claims: list[dict[str, object]], events: list[dict[str, object]]
    ) -> float:
        active = _clamp01(len(claims) + _count_entity_events(entity, events))
        focus = _focus_ratio(entity, claims, events, self._focus, self._hot)
        fresh = _freshness(events)
        info = _info_ratio(claims)
        return _W_ACTIVE * active + _W_FOCUS * focus + _W_FRESH * fresh + _W_INFO * info


def _count_entity_events(entity: str, events: list[dict[str, object]]) -> int:
    norm = _norm_company(entity)
    n = 0
    for ev in events:
        for eid in _as_list(ev.get("entity_ids")):
            if _norm_company(str(eid)) == norm:
                n += 1
    return n


def _focus_ratio(
    entity: str,
    claims: list[dict[str, object]],
    events: list[dict[str, object]],
    focus: list[str],
    hot: list[str],
) -> float:
    """该企业相关文本命中 core/热点 的比例（无相关文本则回退 0）。"""
    texts: list[str] = []
    for c in claims:
        texts.append(str(c.get("claim_text") or ""))
    for ev in events:
        ev_names = [_norm_company(str(eid)) for eid in _as_list(ev.get("entity_ids"))]
        if _norm_company(entity) in ev_names:
            texts.append(str(ev.get("title") or ""))
    if not texts:
        return 0.0
    terms = focus + hot
    if not terms:
        return 0.0
    hit = sum(1 for t in texts if _matches_any(t, terms))
    return hit / len(texts)


def _freshness(events: list[dict[str, object]]) -> float:
    """相关事件的新鲜度：最新事件日期距离今天越近越接近 1。"""
    dates: list[str] = []
    for ev in events:
        d = str(ev.get("event_date") or "")
        if d:
            dates.append(d)
    if not dates:
        return 0.0
    latest = max(dates)
    try:
        raw = latest.split("T")[0]
        dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return 0.0
    days = (datetime.now(UTC) - dt).days
    return _clamp01(1.0 - max(days, 0) / 7.0)


def _info_ratio(claims: list[dict[str, object]]) -> float:
    if not claims:
        return 0.0
    ok = sum(
        1 for c in claims if (isinstance(c.get("evidence"), list) and c["evidence"])
    )
    return ok / len(claims)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _as_list(value: object | None) -> list[object]:
    if not isinstance(value, list):
        return []
    return value


# -------- 顶层：合并候选 + 打分排序（供 engine 调用） --------

def discover_companies(
    bundle: Any,
    provider: LLMProvider | None = None,
    prompt_template: str = "",
) -> list[dict[str, object]]:
    """完全动态发现企业池，返回按关联度降序的 top N（含 name/score/动态文案）。

    候选 = claims.entity_id ∪ events.entity_ids ∪ LLM 从新闻提取的企业（去重）。
    无 provider / LLM 失败时，LLM 候选为空，只用前两者 —— 仍能发现非种子（claims 内）。
    返回 dict 含 name / score / activity_text，供企业节上屏；无候选返回空列表。
    """
    claims = bundle.claims if _is_list(bundle.claims) else []
    events = bundle.events if _is_list(bundle.events) else []

    # 1) 既有来源：claims.entity_id + events.entity_ids
    candidates: list[str] = []
    for c in claims:
        eid = _norm_company(str(c.get("entity_id") or ""))
        if eid and eid not in candidates:
            candidates.append(eid)
    for ev in events:
        for eid_obj in _as_list(ev.get("entity_ids")):
            norm = _norm_company(str(eid_obj))
            if norm and norm not in candidates:
                candidates.append(norm)

    # 2) LLM 提取的企业（去重并入）——本段被报道/讨论企业
    if provider is not None:
        discoverer = CompanyDiscoverer(provider=provider, prompt_template=prompt_template)
        event_bodies = getattr(bundle, "event_body", None) or {}
        picked = _pick_company_events(bundle, events)
        for name in discoverer.discover(picked, event_bodies):
            if name not in candidates:
                candidates.append(name)

    # 3) 确定性打分排序
    scorer = CompanyScorer(
        focus_terms=list(getattr(bundle, "focus_terms", []) or []),
        hot_topics=list(getattr(bundle, "hot_topics", []) or []),
    )
    top = scorer.score_entities(candidates, claims, events)
    return _attach_activity(top, claims, events)


def _pick_company_events(
    bundle: Any, events: list[dict[str, object]]
) -> list[dict[str, object]]:
    """供 LLM 提取企业用的候选事件：按 _filter_events 语义的 top 事件（与推送一致）。

    复用 briefing.pick_top_events（命中 core 且不命中 exclude、日期倒序、热点优先），
    保证 LLM 看到的是真实会进推送的新闻，而非全部。
    """
    try:
        from industry_intelligence.intelligence.briefing import pick_top_events

        return list(pick_top_events(bundle, limit=15))
    except Exception:  # noqa: BLE001 — 提取失败退回全部 events
        return list(events[:_MAX_COMPANIES * 3])


def _attach_activity(
    top: list[dict[str, object]],
    claims: list[dict[str, object]],
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    """给每个上榜企业附一句动态文案（优先 claim 事实/推断，其次事件标题）。"""
    claim_by: dict[str, list[dict[str, object]]] = {}
    event_by: dict[str, list[dict[str, object]]] = {}
    for c in claims:
        eid = _norm_company(str(c.get("entity_id") or ""))
        if eid:
            claim_by.setdefault(eid, []).append(c)
    for ev in events:
        for eid_obj in _as_list(ev.get("entity_ids")):
            norm = _norm_company(str(eid_obj))
            if norm:
                event_by.setdefault(norm, []).append(ev)
    out: list[dict[str, object]] = []
    for item in top:
        name = str(item["name"])
        text = _activity_text(name, claim_by, event_by)
        if not text:
            continue  # 无动态文案的不上屏（不占位）
        out.append({**item, "activity_text": text})
    return out


def _activity_text(
    entity: str,
    claim_by: dict[str, list[dict[str, object]]],
    event_by: dict[str, list[dict[str, object]]],
) -> str:
    """企业的一句话动态文案：优先分析主张，其次最新事件标题。"""
    claims = claim_by.get(entity)
    if claims:
        top = claims[0]
        label = "[事实]" if top.get("claim_type") == CLAIM_TYPE_FACT else "[推断]"
        text = str(top.get("claim_text") or "").strip()
        if text:
            return f"{label} {text}"
    events = event_by.get(entity)
    if events:
        title = str(events[0].get("title") or "").strip()
        if title:
            return f"[事件] {title}"
    return ""


def _is_list(value: object) -> bool:
    return isinstance(value, list)
