"""动态热点发现：用 LLM 基于行业大方向生成当前热点话题。

用户需求：`充电桩` 等关键词只是大方向锚点，检索不应依赖预先写死的固定
对象（固定企业 / 事件词 / 官方域名），而应在该大方向下"自己发现当前最
热门的话题（热搜）"再据此检索。本模块把大方向词交给 LLM，产出可直接
用于搜索的热点短语。

降级模式与 ObservationExtractor 一致：无 provider 或 LLM 失败返回空列表，
调用方按"未发现热点"处理（SearchPlanner 回退固定三族查询）。
"""

from __future__ import annotations

from industry_intelligence.config.models import TopicProfile
from industry_intelligence.llm.provider import LLMError, LLMProvider

HOT_TOPICS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "当前行业热门话题短语",
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}

_DEFAULT_TEMPLATE = (
    "你是一名产业情报分析师。请根据给定的行业大方向与背景，列出当前"
    "（最近 1-2 周）该行业内最热门的具体话题短语，用于后续联网搜索。"
    "只返回 JSON：{\"topics\": [\"话题1\", \"话题2\", ...]}。"
    "要求：topics 是短语数组；每条必须是具体、可直接用于搜索的短语"
    "（如'液冷超充 800V 平台'、'发改委 充电基础设施 政策'），"
    "不要输出泛泛的行业词，不要重复大方向词本身，不要输出空串。"
)


class HotTopicGenerator:
    """基于大方向词用 LLM 生成当前热点话题短语。"""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        prompt_template: str = "",
    ) -> None:
        self._provider = provider
        self._template = prompt_template or _DEFAULT_TEMPLATE

    def generate(
        self,
        topic: TopicProfile,
        focus: list[str] | None = None,
        max_topics: int = 10,
    ) -> list[str]:
        """返回热点短语列表；无 provider 或 LLM 失败返回空列表。"""
        if self._provider is None:
            return []
        try:
            raw = self._provider.generate_structured(
                self._build_prompt(topic, focus, max_topics), HOT_TOPICS_SCHEMA
            )
        except LLMError:
            return []
        return _parse_topics(raw, max_topics)

    def _build_prompt(
        self,
        topic: TopicProfile,
        focus: list[str] | None,
        max_topics: int,
    ) -> str:
        """拼接模板 + 行业上下文（行业数据运行时来自 Topic 配置，模板零行业硬编码）。"""
        lines = [
            self._template,
            "",
            "行业大方向（核心词）：" + "、".join(focus or topic.keywords.core),
            "产品/服务：" + "、".join(topic.keywords.products),
            "市场：" + "、".join(topic.keywords.market),
            "技术：" + "、".join(topic.keywords.technology),
            "重点企业："
            + "、".join(c.canonical_name for c in topic.entities.companies),
            "关注地区：" + "、".join(topic.scope.regions),
            f"输出条数：{max_topics}",
        ]
        return "\n".join(lines)


def _parse_topics(raw: dict[str, object], max_topics: int) -> list[str]:
    """容错解析 LLM 返回：非 list / 非字符串 / 空串 / 重复丢弃，截断到上限。"""
    topics = raw.get("topics")
    if not isinstance(topics, list):
        return []
    out: list[str] = []
    for item in topics:
        if not isinstance(item, str):
            continue
        phrase = item.strip()
        if phrase and phrase not in out:
            out.append(phrase)
        if len(out) >= max_topics:
            break
    return out
