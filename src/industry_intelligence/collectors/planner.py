"""搜索计划生成器。

根据 Topic + Task 生成可追踪、可重复的 QueryPlan 列表。
生成查询族（v0.7.0a5 起热点族优先）：
- 热点族：LLM 动态发现的当前行业热点话题 × 地区（family="hot"，
  每条热点短语受 max_hot 上限约束；热点可用时仅生成该族）
- 兜底三族（热点不可用 / 热点组合为空时回退）：
  - 企业族：核心词 × 企业 × 地区（每组企业受 max_per_entity 上限约束）
  - 事件族：核心词 × 事件词 × 地区（每组事件词受 max_per_category 上限约束）
  - 官方站点族：核心词 × 权威官方域名（topic.official_domains，site: 限定，
    每组域名受 max_per_category 上限约束；无官方域名时该族为空）
同次运行内按 query_string 指纹去重，总数量受 max_queries 上限约束。
"""

from __future__ import annotations

import hashlib
from itertools import product

from industry_intelligence.config.models import TaskConfig, TopicProfile
from industry_intelligence.sources.models import QueryBudget, QueryPlan


class SearchPlanner:
    """生成查询计划。"""

    def __init__(self, budget: QueryBudget | None = None) -> None:
        self._budget = budget or QueryBudget()

    def generate_plans(
        self,
        topic: TopicProfile,
        task: TaskConfig,
        hot_topics: list[str] | None = None,
    ) -> list[QueryPlan]:
        """由 Topic + Task 生成查询计划列表。

        hot_topics 非空时仅生成热点族（大方向下动态发现的热门话题优先）；
        为空或热点组合为空时回退固定三族（保持既有行为）。
        """
        if not task.enabled:
            return []

        regions = self._effective_regions(topic, task)
        companies = self._effective_companies(topic, task)
        focus = self._effective_focus(topic, task)

        if hot_topics:
            candidates = self._build_hot_candidates(hot_topics, regions)
            if not candidates:
                candidates = self._build_legacy_candidates(
                    companies, focus, regions, topic
                )
        else:
            candidates = self._build_legacy_candidates(
                companies, focus, regions, topic
            )

        seen: set[str] = set()
        plans: list[QueryPlan] = []
        for query_string, family in candidates:
            if query_string in seen:
                continue
            seen.add(query_string)
            plans.append(
                QueryPlan(
                    query_id=_fingerprint(query_string),
                    query_string=query_string,
                    family=family,
                )
            )
        return plans[: self._budget.max_queries]

    def _build_hot_candidates(
        self, hot_topics: list[str], regions: list[str]
    ) -> list[tuple[str, str]]:
        """热点族：热点短语 × 地区（受 max_hot 上限约束）。"""
        candidates: list[tuple[str, str]] = []
        for phrase in hot_topics[: self._budget.max_hot]:
            for region in regions:
                candidates.append((_compose(phrase, region), "hot"))
        return candidates

    def _build_legacy_candidates(
        self,
        companies: list[str],
        focus: list[str],
        regions: list[str],
        topic: TopicProfile,
    ) -> list[tuple[str, str]]:
        """兜底三族：企业 / 事件词 / 官方站点（保持既有生成顺序与预算）。"""
        candidates: list[tuple[str, str]] = []
        for company in companies:
            for group, (core, region) in enumerate(product(focus, regions)):
                if group >= self._budget.max_per_entity:
                    break
                candidates.append((_compose(core, company, region), "company"))
        for event in topic.keywords.events:
            for group, (core, region) in enumerate(product(focus, regions)):
                if group >= self._budget.max_per_category:
                    break
                candidates.append((_compose(core, event, region), "event"))
        for domain in topic.official_domains:
            for group, core in enumerate(focus):
                if group >= self._budget.max_per_category:
                    break
                candidates.append((_compose(core, f"site:{domain}"), "official"))
        return candidates

    @staticmethod
    def _effective_regions(topic: TopicProfile, task: TaskConfig) -> list[str]:
        if task.overrides is not None and task.overrides.regions is not None:
            return task.overrides.regions
        return list(topic.scope.regions)

    @staticmethod
    def _effective_companies(topic: TopicProfile, task: TaskConfig) -> list[str]:
        if task.overrides is not None and task.overrides.companies is not None:
            return task.overrides.companies
        return [c.canonical_name for c in topic.entities.companies]

    @staticmethod
    def _effective_focus(topic: TopicProfile, task: TaskConfig) -> list[str]:
        if task.overrides is not None and task.overrides.focus is not None:
            return task.overrides.focus
        return list(topic.keywords.core)


def _compose(*terms: str) -> str:
    """将词条组合为查询字符串（去空白后以空格连接）。"""
    parts = [t.strip() for t in terms if t and t.strip()]
    return " ".join(parts)


def _fingerprint(query_string: str) -> str:
    """查询指纹：sha256 前 16 位，用于同次运行内去重。"""
    return hashlib.sha256(query_string.encode("utf-8")).hexdigest()[:16]
