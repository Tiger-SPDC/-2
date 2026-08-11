"""事件分类：将文档归入事件类型。

LLM 主路径（结构化输出）失败或无 provider 时，回落关键词匹配。
关键词 → 事件类型映射表在代码中维护（未来可移入配置）。
"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.llm.provider import LLMError, LLMProvider

# 事件关键词 → event_type_id（覆盖充电桩等场景的通用词）
_KEYWORD_EVENT_MAP: dict[str, str] = {
    "政策": "policy_regulation",
    "监管": "policy_regulation",
    "补贴": "policy_regulation",
    "法规": "policy_regulation",
    "标准": "policy_regulation",
    "招标": "bid_order",
    "中标": "bid_order",
    "订单": "bid_order",
    "发布": "new_product",
    "新品": "new_product",
    "上线": "new_product",
    "扩产": "capacity_build",
    "投产": "capacity_build",
    "投资": "investment_expansion",
    "融资": "financing",
    "并购": "m_and_a",
    "收购": "m_and_a",
    "合作": "cooperation",
    "签约": "cooperation",
    "渠道": "channel_expansion",
    "出海": "overseas_expansion",
    "海外": "overseas_expansion",
    "价格": "price_change",
    "降价": "price_change",
    "销量": "market_sales",
    "出货": "market_sales",
    "召回": "recall_accident",
    "事故": "recall_accident",
    "质量": "recall_accident",
    "人事": "personnel_change",
    "任命": "personnel_change",
    "离职": "personnel_change",
    "诉讼": "litigation_compliance",
    "合规": "litigation_compliance",
}

_DEFAULT_TEMPLATE = (
    "你是一名产业情报分析师。请把下面的新闻报道归入某个事件类型，"
    "只返回 JSON：{\"event_type_id\": \"<ID>\", \"reason\": \"<一句话理由>\"}。"
    "event_type_id 必须来自允许列表。"
)


class EventClassifier:
    """文档 → event_type_id 分类器。"""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        event_types: dict[str, str] | None = None,
        keywords: list[str] | None = None,
        keyword_map: dict[str, str] | None = None,
        prompt_template: str = "",
    ) -> None:
        self._provider = provider
        self._event_types = dict(event_types) if event_types else {}
        self._keywords = list(keywords) if keywords else []
        self._keyword_map = keyword_map or _KEYWORD_EVENT_MAP
        self._template = prompt_template or _DEFAULT_TEMPLATE

    def classify(self, doc: NormalizedDocument) -> str:
        """返回 event_type_id；LLM 与关键词均不命中时返回 "other"。"""
        if self._provider:
            try:
                event_type_id = self._classify_llm(doc)
            except LLMError:
                event_type_id = None
            if event_type_id:
                return event_type_id
        return self.keyword_match(doc) or "other"

    def keyword_match(self, doc: NormalizedDocument) -> str | None:
        """基于 ``topic.keywords.events`` 关键词回落匹配。"""
        text = "\n".join(p for p in (doc.title, doc.content_text) if p).casefold()
        for keyword in self._keywords:
            event_type_id = self._keyword_map.get(keyword)
            if event_type_id and keyword.casefold() in text:
                return event_type_id
        return None

    def _classify_llm(self, doc: NormalizedDocument) -> str | None:
        if self._provider is None:
            return None
        schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "event_type_id": {"type": "string", "enum": list(self._event_types)},
                "reason": {"type": "string"},
            },
            "required": ["event_type_id", "reason"],
            "additionalProperties": False,
        }
        result = self._provider.generate_structured(self._build_prompt(doc), schema)
        event_type_id = result.get("event_type_id")
        if isinstance(event_type_id, str) and event_type_id in self._event_types:
            return event_type_id
        return None

    def _build_prompt(self, doc: NormalizedDocument) -> str:
        types_desc = "\n".join(f"- {tid}: {name}" for tid, name in self._event_types.items())
        return "\n".join(
            [
                self._template,
                "",
                "允许的事件类型：",
                types_desc,
                "",
                f"新闻标题：{doc.title}",
                "",
                "正文：",
                doc.content_text,
            ]
        )
