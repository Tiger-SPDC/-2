"""指标观测数据模型。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def create_observation_id(
    document_id: str, metric_id: str, entity_id: str, value: float
) -> str:
    """确定性观测 ID：同一输入可重复计算（前 16 位 hex）。"""
    key = f"{document_id}|{metric_id}|{entity_id}|{value:.6g}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class Observation:
    """从单篇文档抽取的一条可量化指标观测。"""

    observation_id: str
    document_id: str
    metric_id: str
    entity_id: str
    value: float
    unit: str
    period_start: str | None
    period_end: str | None
    region: str | None
    confidence: float
    evidence_text: str
