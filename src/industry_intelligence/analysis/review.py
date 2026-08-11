"""质量审查 Agent（Phase 4）：对分析 Claim 执行 7 项检查，产出通过/拒绝/降级结论。

Review Agent 在 Pipeline 中独立于 AnalysisEngine 运行（可选）：
读取该 run 的全部 Claim + Evidence，用 LLM 按 config/prompts/review.md 模板
执行 7 项检查（数字可追溯/日期/推断≠事实/活动度≠销量/证据/矛盾/措辞），
结果写入 claim_reviews 表。无 provider 或 review 关闭时返回空 ReviewResult（不报错）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256

from industry_intelligence.analysis.base import _row_value
from industry_intelligence.config.models import ReviewConfig, TaskConfig, TopicProfile
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore

REVIEW_PASS = "pass"
REVIEW_REJECT = "reject"
REVIEW_DOWNGRADE = "downgrade"
REVIEW_VERDICTS = frozenset({REVIEW_PASS, REVIEW_REJECT, REVIEW_DOWNGRADE})

CLAIM_TYPES = frozenset({"fact", "inference", "forecast", "unknown"})

#: 与 config/prompts/review.md 期望输出一致的 JSON Schema
REVIEW_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["pass", "reject", "downgrade"],
                    },
                    "downgrade_to": {
                        "type": "string",
                        "enum": ["fact", "inference", "forecast", "unknown"],
                    },
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["claim_id", "verdict"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reviews"],
    "additionalProperties": False,
}


def make_review_id(claim_id: str, verdict: str, run_id: str) -> str:
    """确定性 review_id：sha256(claim_id|verdict|run_id)[:16]。
    """
    payload = f"{claim_id}|{verdict}|{run_id}"
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class ReviewResult:
    """一次审查运行的结果汇总（供 Pipeline 与报告引擎消费）。"""

    run_id: str
    reviews: list[dict[str, object]] = field(default_factory=list)
    passed: int = 0
    rejected: int = 0
    downgraded: int = 0
    errors: list[str] = field(default_factory=list)


class ReviewAgent:
    """质量审查 Agent：注入 claims + evidence → LLM 7 项检查 → 持久化结论。"""

    def __init__(
        self,
        provider: LLMProvider | None,
        sqlite_store: SQLiteStore,
        prompt_template: str,
        topic: TopicProfile,
        task: TaskConfig,
        review_config: ReviewConfig | None = None,
    ) -> None:
        self._provider = provider
        self._store = sqlite_store
        self._prompt_template = prompt_template
        self._topic = topic
        self._task = task
        self._config = review_config or ReviewConfig()

    def review(self, run_id: str) -> ReviewResult:
        """执行审查：读取 claims+evidence，LLM 检查，持久化，返回汇总。"""
        result = ReviewResult(run_id=run_id)
        if not self._config.enabled or self._provider is None:
            return result
        claims = self._collect_claims(run_id)
        if not claims:
            return result

        raw = self._generate_structured_safe(
            self._build_prompt(claims), result.errors
        )
        reviews_raw = raw.get("reviews")
        if not isinstance(reviews_raw, list):
            if raw:
                result.errors.append("review: LLM 未返回 reviews 数组")
            return result

        seen: set[str] = set()
        for item in reviews_raw:
            if not isinstance(item, dict):
                continue
            claim_id = item.get("claim_id")
            if not isinstance(claim_id, str) or claim_id not in claims:
                continue
            if claim_id in seen:
                continue
            seen.add(claim_id)
            self._persist_review(item, run_id, result)
        return result

    # ------------------------------------------------------------------ 内部

    def _collect_claims(self, run_id: str) -> dict[str, list[dict[str, object]]]:
        """按 claim_id 分组读取 claims + evidence（一条 Claim 多条证据时合并）。"""
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in self._store.query_claims_with_evidence(run_id):
            claim_id = str(_row_value(row, "claim_id", ""))
            if not claim_id:
                continue
            doc = str(_row_value(row, "document_id", "") or "")
            obs = str(_row_value(row, "observation_id", "") or "")
            entry: dict[str, object] = {
                "claim_id": claim_id,
                "claim_text": str(_row_value(row, "claim_text", "")),
                "claim_type": str(_row_value(row, "claim_type", "unknown")),
                "confidence": _row_value(row, "confidence", 0.0),
                "entity_id": _row_value(row, "entity_id", None),
                "analysis_type": str(_row_value(row, "analysis_type", "")),
                "evidence_role": str(_row_value(row, "evidence_role", "")),
            }
            if doc:
                entry["document_id"] = doc
            if obs:
                entry["observation_id"] = obs
            grouped.setdefault(claim_id, []).append(entry)
        return grouped

    def _build_prompt(self, claims: Mapping[str, list[dict[str, object]]]) -> str:
        """把 claims + evidence 序列化为 review 输入。"""
        lines = [
            f"待审查分析结论数：{len(claims)}",
            f"主题：{self._topic.id}",
            "",
            "## 分析结论与证据",
        ]
        for claim_id in sorted(claims):
            entries = claims[claim_id]
            first = entries[0]
            lines.append(
                f"\n- claim_id: {claim_id}"
                f"\n  文本: {first.get('claim_text', '')}"
                f"\n  类型: {first.get('claim_type', 'unknown')} | "
                f"置信度: {first.get('confidence', 0.0)} | "
                f"维度: {first.get('analysis_type', '')}"
            )
            for ev in entries:
                ev_desc = (
                    f"文档 {ev.get('document_id')}"
                    if "document_id" in ev
                    else f"观测 {ev.get('observation_id')}"
                )
                lines.append(f"  证据[{ev.get('evidence_role', '')}]: {ev_desc}")
        return "\n".join(lines)

    def _generate_structured_safe(
        self, prompt: str, errors: list[str]
    ) -> dict[str, object]:
        """调用 LLM 结构化输出；失败记录错误返回 {}，不抛出。"""
        if self._provider is None:
            return {}
        try:
            return self._provider.generate_structured(prompt, REVIEW_SCHEMA)
        except LLMError as exc:
            errors.append(f"review: {exc}")
            return {}

    def _persist_review(
        self, item: dict[str, object], run_id: str, result: ReviewResult
    ) -> None:
        """校验并持久化单条 review 结论；统计到 ReviewResult。"""
        claim_id = str(item.get("claim_id") or "")
        verdict = str(item.get("verdict") or "")
        if verdict not in REVIEW_VERDICTS:
            result.errors.append(f"review: invalid verdict {verdict!r} for {claim_id}")
            return
        downgrade_to = item.get("downgrade_to")
        if verdict == REVIEW_DOWNGRADE:
            if downgrade_to not in CLAIM_TYPES:
                result.errors.append(
                    f"review: downgrade requires downgrade_to for {claim_id}"
                )
                return
        else:
            downgrade_to = None
        raw_issues = item.get("issues", [])
        issues = (
            [str(x) for x in raw_issues if isinstance(x, str)]
            if isinstance(raw_issues, list)
            else []
        )
        reason = str(item.get("reason") or "")
        review_id = make_review_id(claim_id, verdict, run_id)
        try:
            self._store.insert_claim_review(
                review_id,
                claim_id,
                verdict,
                run_id,
                downgrade_to=(
                    str(downgrade_to) if downgrade_to is not None else None
                ),
                issues=issues,
                reason=reason,
            )
        except Exception as exc:  # noqa: BLE001 — 单条写入失败不中断
            result.errors.append(f"review persist {claim_id}: {exc}")
            return
        result.reviews.append(
            {
                "claim_id": claim_id,
                "verdict": verdict,
                "downgrade_to": downgrade_to,
                "issues": issues,
                "reason": reason,
            }
        )
        if verdict == REVIEW_PASS:
            result.passed += 1
        elif verdict == REVIEW_REJECT:
            result.rejected += 1
        else:
            result.downgraded += 1
