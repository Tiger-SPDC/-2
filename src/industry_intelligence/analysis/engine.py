"""汇聚分析引擎（Phase 3）：编排 4 个分析师，持久化 Claim/Evidence，计算覆盖率。

各分析师独立 try/except，单个失败不终止整体；
分析结果全部写入 SQLite（claims / claim_evidence），保证可追溯；
Evidence Coverage = 有证据的 Claim 数 / 全部 Claim 数。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from industry_intelligence.analysis.base import AnalysisAgent
from industry_intelligence.analysis.competitor import CompetitorAnalyst
from industry_intelligence.analysis.market import MarketAnalyst
from industry_intelligence.analysis.models import (
    ANALYSIS_COMPETITOR,
    ANALYSIS_MARKET,
    ANALYSIS_RISK,
    ANALYSIS_TECHNOLOGY,
    AnalysisResult,
    TrendIndicator,
)
from industry_intelligence.analysis.risk import RiskAnalyst
from industry_intelligence.analysis.technology import TechnologyAnalyst
from industry_intelligence.config.models import AnalysisConfig, TaskConfig, TopicProfile
from industry_intelligence.llm.provider import LLMProvider
from industry_intelligence.storage import SQLiteStore

#: 分析维度 → 分析师类
_ANALYST_FACTORIES: dict[str, type[AnalysisAgent]] = {
    ANALYSIS_COMPETITOR: CompetitorAnalyst,
    ANALYSIS_MARKET: MarketAnalyst,
    ANALYSIS_TECHNOLOGY: TechnologyAnalyst,
    ANALYSIS_RISK: RiskAnalyst,
}


@dataclass
class EngineResult:
    """一次分析引擎运行的结果汇总。"""

    run_id: str
    results: list[AnalysisResult] = field(default_factory=list)
    analysis_claims: int = 0
    evidence_coverage: float = 0.0
    trends: dict[str, list[TrendIndicator]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AnalysisEngine:
    """编排全部启用维度的分析师，持久化分析结果并计算证据覆盖率。"""

    def __init__(
        self,
        *,
        provider: LLMProvider | None,
        sqlite_store: SQLiteStore,
        topic: TopicProfile,
        task: TaskConfig,
        prompts: Mapping[str, str] | None = None,
        analysis_config: AnalysisConfig | None = None,
    ) -> None:
        self._provider = provider
        self._store = sqlite_store
        self._topic = topic
        self._task = task
        self._prompts = prompts or {}
        self._analysis_config = analysis_config or AnalysisConfig()

    def run(self, run_id: str) -> EngineResult:
        result = EngineResult(run_id=run_id)

        for analysis_type in self._analysis_config.enabled_dimensions:
            if analysis_type not in _ANALYST_FACTORIES:
                result.errors.append(
                    f"analysis: unknown dimension {analysis_type!r}"
                )
                continue
            try:
                analysis = self._analyst(analysis_type).analyze(run_id)
            except Exception as exc:  # noqa: BLE001 — 单分析师失败不中断
                result.errors.append(f"analysis {analysis_type}: {exc}")
                continue
            result.errors.extend(analysis.errors)
            try:
                self._persist_analysis(analysis)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"persist {analysis_type}: {exc}")
            result.results.append(analysis)

        try:
            from industry_intelligence.analysis.historical import (
                HistoricalComparison,
            )

            result.trends = HistoricalComparison(
                self._store, self._task, self._topic
            ).compute_trends(self._topic.id)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"historical trends: {exc}")

        result.analysis_claims = self._count_claims(run_id)
        result.evidence_coverage = self._compute_coverage(run_id)
        return result

    # ------------------------------------------------------------------ 内部

    def _analyst(self, analysis_type: str) -> AnalysisAgent:
        return _ANALYST_FACTORIES[analysis_type](
            self._provider,
            self._store,
            self._prompts.get(analysis_type, ""),
            self._topic,
            self._task,
        )

    def _persist_analysis(self, analysis: AnalysisResult) -> None:
        """把单个维度的 Claim 与 Evidence 写入 SQLite。"""
        for claim in analysis.claims:
            self._store.insert_claim(
                claim.claim_id,
                claim.claim_text,
                claim.claim_type,
                claim.confidence,
                claim.analysis_type,
                claim.topic_id,
                claim.run_id,
                entity_id=claim.entity_id,
            )
        for ev in analysis.evidences:
            self._store.insert_claim_evidence(
                ev.claim_id,
                document_id=ev.document_id,
                observation_id=ev.observation_id,
                evidence_role=ev.evidence_role,
            )

    def _count_claims(self, run_id: str) -> int:
        return len(self._store.query_claims(run_id))

    def _compute_coverage(self, run_id: str) -> float:
        """有证据的 Claim 数 / 全部 Claim 数（基于持久化结果计算）。"""
        claims = self._store.query_claims(run_id)
        if not claims:
            return 0.0
        covered = sum(
            1
            for row in claims
            if self._store.query_claim_evidence(row["claim_id"])
        )
        return round(covered / len(claims), 4)
