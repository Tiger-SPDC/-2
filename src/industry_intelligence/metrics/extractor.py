"""Observation 抽取：用 LLM 结构化输出从文档提取可量化指标。

只抽取文本中显式给出的数值，不推断缺失数据；置信度过低者过滤。
"""

from __future__ import annotations

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.metrics.models import Observation, create_observation_id

_DEFAULT_TEMPLATE = (
    "你是一名产业数据分析师。从下面的新闻文本中抽取可量化的产业指标观测值，"
    "只返回 JSON：{\"observations\": [...]}。"
    "metric_id 与 entity_id 必须来自允许列表，只抽取文中明确给出的数值。"
)


class ObservationExtractor:
    """文档 → 观测列表（置信度 < 阈值者丢弃）。"""

    def __init__(
        self,
        provider: LLMProvider,
        prompt_template: str = "",
        confidence_threshold: float = 0.5,
    ) -> None:
        self._provider = provider
        self._template = prompt_template or _DEFAULT_TEMPLATE
        self._threshold = confidence_threshold

    def extract(
        self,
        doc: NormalizedDocument,
        metrics: list[str],
        entities: list[str],
    ) -> list[Observation]:
        """抽取观测；无文本 / 无允许项 / LLM 失败时返回空列表。"""
        if not entities or not metrics:
            return []
        text = "\n".join(p for p in (doc.title, doc.content_text) if p)
        if not text.strip():
            return []
        schema = self._build_schema(metrics, entities)
        try:
            result = self._provider.generate_structured(
                self._build_prompt(doc, metrics, entities), schema
            )
        except LLMError:
            return []
        return self._parse(result, doc)

    def _build_schema(self, metrics: list[str], entities: list[str]) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric_id": {"type": "string", "enum": metrics},
                            "entity_id": {"type": "string", "enum": entities},
                            "value": {"type": "number"},
                            "unit": {"type": "string"},
                            "period_start": {"type": "string"},
                            "period_end": {"type": "string"},
                            "region": {"type": "string"},
                            "confidence": {"type": "number"},
                            "evidence_text": {"type": "string"},
                        },
                        "required": ["metric_id", "entity_id", "value", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["observations"],
            "additionalProperties": False,
        }

    def _build_prompt(
        self, doc: NormalizedDocument, metrics: list[str], entities: list[str]
    ) -> str:
        return "\n".join(
            [
                self._template,
                "",
                "允许的指标（metric_id）：",
                ", ".join(metrics),
                "",
                "允许的实体（entity_id）：",
                ", ".join(entities),
                "",
                f"新闻标题：{doc.title}",
                "",
                "正文：",
                doc.content_text,
            ]
        )

    def _parse(self, result: dict[str, object], doc: NormalizedDocument) -> list[Observation]:
        raw = result.get("observations")
        if not isinstance(raw, list):
            return []
        observations: list[Observation] = []
        for item in raw:
            obs = self._to_observation(item, doc)
            if obs is not None:
                observations.append(obs)
        return observations

    def _to_observation(
        self, item: object, doc: NormalizedDocument
    ) -> Observation | None:
        if not isinstance(item, dict):
            return None
        metric_id = item.get("metric_id")
        entity_id = item.get("entity_id")
        if not isinstance(metric_id, str) or not isinstance(entity_id, str):
            return None
        value = _to_float(item.get("value"))
        confidence = _to_float(item.get("confidence", 0.0))
        if value is None or confidence is None:
            return None
        if confidence < self._threshold:
            return None
        return Observation(
            observation_id=create_observation_id(
                doc.document_id, metric_id, entity_id, value
            ),
            document_id=doc.document_id,
            metric_id=metric_id,
            entity_id=entity_id,
            value=value,
            unit=str(item.get("unit") or ""),
            period_start=_opt_str(item.get("period_start")),
            period_end=_opt_str(item.get("period_end")),
            region=_opt_str(item.get("region")),
            confidence=confidence,
            evidence_text=str(item.get("evidence_text") or ""),
        )


def _opt_str(value: object | None) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _to_float(value: object | None) -> float | None:
    """仅接受数值类型；bool / None / 字符串都不当数值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
