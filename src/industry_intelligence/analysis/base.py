"""分析 Agent 抽象基类（Phase 3）。

所有分析 Agent 共享：LLM/SQLite 注入、系统 prompt、确定性 claim_id、
LLM 结构化输出安全包装、Claim 构造与证据兜底。
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Callable

from industry_intelligence.analysis.models import (
    CLAIM_TYPES,
    AnalysisResult,
    Claim,
    ClaimEvidence,
    make_claim_id,
)
from industry_intelligence.config.models import TaskConfig, TopicProfile
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.storage import SQLiteStore


def _row_value(row: object, key: str, default: object) -> object:
    """从 sqlite3.Row / dict / dataclass 中取字段，兼容三种输入。"""
    if isinstance(row, sqlite3.Row):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_float_value(value: object, default: float) -> float:
    """把 object 安全转 float；bool / 非数值返回 default。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def build_claims_schema(
    extra_properties: dict[str, object] | None = None,
) -> dict[str, object]:
    """构建分析师通用的 claims JSON Schema；可按需追加额外字段（如 severity）。"""
    properties: dict[str, object] = {
        "claim_text": {"type": "string"},
        "claim_type": {
            "type": "string",
            "enum": ["fact", "inference", "forecast", "unknown"],
        },
        "confidence": {"type": "number"},
        "entity_id": {"type": "string"},
        "evidence_document_ids": {"type": "array", "items": {"type": "string"}},
        "evidence_observation_ids": {"type": "array", "items": {"type": "string"}},
    }
    if extra_properties:
        properties.update(extra_properties)
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": ["claim_text", "claim_type", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }


class AnalysisAgent(ABC):
    """分析 Agent 抽象：query → LLM 合成 → Claim + Evidence → AnalysisResult。"""

    #: 子类覆写：分析维度（competitor/market/technology/risk）
    analysis_type: str = ""

    def __init__(
        self,
        provider: LLMProvider | None,
        sqlite_store: SQLiteStore,
        prompt_template: str,
        topic: TopicProfile,
        task: TaskConfig,
    ) -> None:
        self._provider = provider
        self._store = sqlite_store
        self._prompt_template = prompt_template
        self._topic = topic
        self._task = task

    @abstractmethod
    def analyze(self, run_id: str) -> AnalysisResult:
        """执行分析并返回 AnalysisResult；单步失败记录到 errors，不中断。"""

    # ------------------------------------------------------------------ 助手

    def _build_messages(self, prompt: str) -> list[dict[str, str]]:
        """构建 LLM 消息列表（单条 user = 模板 + 本次输入）。

        DeepSeek json_object 模式只检查 user 消息；与分类器/提取器一致，
        模板与数据合并进同一 user 消息，模型才能按 schema 输出结构。
        """
        content = (
            f"{self._prompt_template}\n\n{prompt}" if self._prompt_template else prompt
        )
        return [{"role": "user", "content": content}]

    def _claim_id(self, claim_text: str, run_id: str) -> str:
        """确定性 claim_id：sha256(claim_text|analysis_type|run_id)[:16]。"""
        return make_claim_id(claim_text, self.analysis_type, run_id)

    def _generate_structured_safe(
        self,
        prompt: str,
        json_schema: dict[str, object],
        errors: list[str],
    ) -> dict[str, object]:
        """调用 LLM 结构化输出；失败返回 {} 并记录错误，不抛出。

        模板合并进 user 消息（与分类器/提取器的单条 user 模式一致）：
        此前模板存于 ``_prompt_template`` 却从未注入请求，模型只收到裸数据，
        无法按要求输出 claims 结构（DeepSeek json_object 也只检查 user 消息）。
        """
        if self._provider is None:
            return {}
        user_prompt = prompt
        if self._prompt_template:
            user_prompt = f"{self._prompt_template}\n\n{prompt}"
        try:
            return self._provider.generate_structured(user_prompt, json_schema)
        except LLMError as exc:
            errors.append(f"{self.analysis_type}: {exc}")
            return {}

    def _make_claim(
        self,
        item: dict[str, object],
        run_id: str,
        entity_id: str | None = None,
    ) -> Claim | None:
        """从 LLM 输出的单个 claim 字典构造 Claim；不合法返回 None。"""
        text = item.get("claim_text")
        claim_type = item.get("claim_type")
        if not isinstance(text, str) or not text.strip():
            return None
        if claim_type not in CLAIM_TYPES:
            return None
        raw_confidence = item.get("confidence")
        if isinstance(raw_confidence, bool) or not isinstance(
            raw_confidence, (int, float)
        ):
            confidence = 0.5
        else:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        entity = item.get("entity_id") or entity_id
        return Claim(
            claim_id=self._claim_id(text.strip(), run_id),
            claim_text=text.strip(),
            claim_type=str(claim_type),
            confidence=confidence,
            entity_id=entity if isinstance(entity, str) and entity else None,
            analysis_type=self.analysis_type,
            topic_id=self._topic.id,
            run_id=run_id,
        )

    def _evidence_from(
        self,
        claim_id: str,
        document_ids: list[str],
        observation_ids: list[str],
        *,
        fallback_document_ids: list[str] | None = None,
        fallback_observation_ids: list[str] | None = None,
    ) -> list[ClaimEvidence]:
        """从候选证据 ID 构建证据链接；为空时用兜底 ID，保证至少一条证据。

        每条 Claim 至少挂一条 Evidence 是 Phase 3 的质量底线。
        """
        doc_ids = list(document_ids) if document_ids else list(fallback_document_ids or [])
        obs_ids = (
            list(observation_ids) if observation_ids else list(fallback_observation_ids or [])
        )
        evidences: list[ClaimEvidence] = []
        for did in doc_ids[:3]:
            evidences.append(ClaimEvidence(claim_id, document_id=did))
        for oid in obs_ids[:3]:
            evidences.append(ClaimEvidence(claim_id, observation_id=oid))
        return evidences

    def _entity_document_ids(
        self,
        entity_id: str,
        period_start: str,
        period_end: str,
    ) -> list[str]:
        """当前窗口内与某实体匹配的文档 ID（用于证据兜底）。"""
        return [
            row["document_id"]
            for row in self._store.query_documents_by_entity(
                self._topic.id, entity_id,
                start_date=period_start, end_date=period_end,
            )
        ]

    def _extract_claims(
        self,
        raw: dict[str, object],
        run_id: str,
        *,
        valid_docs: set[str] | None = None,
        valid_obs: set[str] | None = None,
        fallback_docs: list[str] | Callable[[str | None], list[str]] | None = None,
        fallback_obs: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> tuple[list[Claim], list[ClaimEvidence]]:
        """从 LLM 返回的 claims 数组构建 Claim + ClaimEvidence。

        证据 ID 只保留在 valid 集合内的真实引用；为空时用兜底 ID 补齐，
        保证每条 Claim 至少一条证据。fallback_docs 可为按 entity 提供的函数。
        """
        claims: list[Claim] = []
        evidences: list[ClaimEvidence] = []
        claims_raw = raw.get("claims")
        if not isinstance(claims_raw, list):
            if errors is not None:
                errors.append(f"{self.analysis_type}: LLM 未返回 claims 数组")
            return claims, evidences
        valid_docs = valid_docs or set()
        valid_obs = valid_obs or set()
        for item in claims_raw:
            if not isinstance(item, dict):
                continue
            entity_raw = item.get("entity_id")
            entity_id = entity_raw if isinstance(entity_raw, str) and entity_raw else None
            claim = self._make_claim(item, run_id, entity_id=entity_id)
            if claim is None:
                continue
            doc_ids = [
                d for d in item.get("evidence_document_ids", [])
                if isinstance(d, str) and d in valid_docs
            ]
            obs_ids = [
                o for o in item.get("evidence_observation_ids", [])
                if isinstance(o, str) and o in valid_obs
            ]
            resolved_fallback = (
                fallback_docs(claim.entity_id)
                if callable(fallback_docs)
                else fallback_docs
            )
            evs = self._evidence_from(
                claim.claim_id,
                doc_ids,
                obs_ids,
                fallback_document_ids=resolved_fallback,
                fallback_observation_ids=fallback_obs,
            )
            claims.append(claim)
            evidences.extend(evs)
        return claims, evidences
