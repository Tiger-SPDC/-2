"""搜索计划生成器。

根据 Topic + Task 生成可追踪、可重复的 QueryPlan 列表。
Phase 1 生成两族查询：
- 企业族：核心词 × 企业 × 地区（每组企业受 max_per_entity 上限约束）
- 事件族：核心词 × 事件词 × 地区（每组事件词受 max_per_category 上限约束）
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

    def generate_plans(self, topic: TopicProfile, task: TaskConfig) -> list[QueryPlan]:
        """由 Topic + Task 生成查询计划列表。"""
        if not task.enabled:
            return []

        regions = self._effective_regions(topic, task)
        companies = self._effective_companies(topic, task)
        focus = self._effective_focus(topic, task)

        candidates: list[str] = []
        for company in companies:
            for group, (core, region) in enumerate(product(focus, regions)):
                if group >= self._budget.max_per_entity:
                    break
                candidates.append(_compose(core, company, region))
        for event in topic.keywords.events:
            for group, (core, region) in enumerate(product(focus, regions)):
                if group >= self._budget.max_per_category:
                    break
                candidates.append(_compose(core, event, region))

        seen: set[str] = set()
        plans: list[QueryPlan] = []
        for query_string in candidates:
            if query_string in seen:
                continue
            seen.add(query_string)
            plans.append(
                QueryPlan(query_id=_fingerprint(query_string), query_string=query_string)
            )
        return plans[: self._budget.max_queries]

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
