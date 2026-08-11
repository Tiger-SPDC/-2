"""Pipeline 控制器：编排采集 → 标准化 → 去重 → 实体/事件/观测分析 → 持久化。

单步失败不中断后续；错误累积到 ``RunResult.errors``，最终报告 partial success。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from industry_intelligence.analysis.engine import AnalysisEngine, EngineResult
from industry_intelligence.analysis.models import AnalysisResult, TrendIndicator
from industry_intelligence.collectors import SearchPlanner
from industry_intelligence.config.models import SystemConfig, TaskConfig, TopicProfile
from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.entities import EntityResolver
from industry_intelligence.intelligence import EventClassifier, EventClusterer
from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics import ObservationExtractor
from industry_intelligence.metrics.models import Observation
from industry_intelligence.normalization import Deduplicator
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.storage.jsonl_store import JSONLStore
from industry_intelligence.storage.sqlite_store import SQLiteStore


@dataclass
class RunResult:
    """一次运行的结果汇总。"""

    run_id: str
    status: str = "running"
    documents_collected: int = 0
    documents_deduped: int = 0
    events_created: int = 0
    observations_extracted: int = 0
    analysis_results: list[AnalysisResult] = field(default_factory=list)
    analysis_claims: int = 0
    evidence_coverage: float = 0.0
    trends: dict[str, list[TrendIndicator]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class Pipeline:
    """Phase 1 + Phase 2 完整链路控制器。"""

    def __init__(
        self,
        *,
        topic: TopicProfile,
        task: TaskConfig,
        system_config: SystemConfig,
        adapter: SourceAdapter,
        jsonl_store: JSONLStore,
        sqlite_store: SQLiteStore,
        entity_resolver: EntityResolver,
        event_classifier: EventClassifier,
        observation_extractor: ObservationExtractor,
        planner: SearchPlanner | None = None,
        dedup: Deduplicator | None = None,
        event_clusterer: EventClusterer | None = None,
        analysis_engine: AnalysisEngine | None = None,
    ) -> None:
        self._topic = topic
        self._task = task
        self._system = system_config
        self._adapter = adapter
        self._jsonl = jsonl_store
        self._sqlite = sqlite_store
        self._resolver = entity_resolver
        self._classifier = event_classifier
        self._extractor = observation_extractor
        self._planner = planner or SearchPlanner()
        self._dedup = dedup if dedup is not None else Deduplicator()
        self._clusterer = event_clusterer or EventClusterer()
        # None → 跳过分析阶段（Phase 3 之前行为完全一致）
        self._analysis_engine = analysis_engine

    def run(self) -> RunResult:
        run_id = uuid.uuid4().hex[:16]
        result = RunResult(run_id=run_id)

        try:
            self._sqlite.insert_run(
                run_id,
                topic_id=self._topic.id,
                task_id=self._task.id,
                started_at=_now_iso(),
            )
        except Exception as exc:  # noqa: BLE001 — 记录失败不中断
            result.errors.append(f"run record: {exc}")

        docs = self._collect(result)
        result.documents_collected = len(docs)

        try:
            docs = [self._resolver.resolve_document(doc) for doc in docs]
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"entity resolve: {exc}")

        doc_event_types: dict[str, str] = {}
        try:
            for doc in docs:
                doc_event_types[doc.document_id] = self._classifier.classify(doc)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"event classify: {exc}")

        events: list[Event] = []
        try:
            events = self._clusterer.cluster(docs, doc_event_types)
            result.events_created = len(events)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"event clustering: {exc}")

        observations: list[Observation] = []
        try:
            for doc in docs:
                observations.extend(
                    self._extractor.extract(doc, self._topic.metrics, doc.matched_entities)
                )
            result.observations_extracted = len(observations)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"observation extraction: {exc}")

        try:
            self._persist(docs, events, observations)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"persist: {exc}")

        if self._analysis_engine is not None:
            self._run_analysis(run_id, result)

        result.status = _final_status(result)
        try:
            self._sqlite.complete_run(
                run_id,
                status=result.status,
                documents_collected=result.documents_collected,
                documents_deduped=result.documents_deduped,
                events_created=result.events_created,
                observations_extracted=result.observations_extracted,
                analysis_claims=result.analysis_claims,
                evidence_coverage=result.evidence_coverage,
                errors=result.errors,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"run complete: {exc}")
        return result

    def _run_analysis(self, run_id: str, result: RunResult) -> EngineResult | None:
        """执行 Phase 3 分析：编排分析师、持久化 Claim、计算覆盖率。"""
        engine = self._analysis_engine
        if engine is None:
            return None
        try:
            analysis = engine.run(run_id)
        except Exception as exc:  # noqa: BLE001 — 分析失败不中断整体
            result.errors.append(f"analysis engine: {exc}")
            return None
        result.analysis_results = analysis.results
        result.analysis_claims = analysis.analysis_claims
        result.evidence_coverage = analysis.evidence_coverage
        result.trends = analysis.trends
        result.errors.extend(analysis.errors)
        return analysis

    def _collect(self, result: RunResult) -> list[NormalizedDocument]:
        """执行搜索计划并采集去重，写入 JSONL。"""
        docs: list[NormalizedDocument] = []
        try:
            plans = self._planner.generate_plans(self._topic, self._task)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"planning: {exc}")
            return docs
        for item in self._adapter.discover(plans, context={}):
            try:
                raw = self._adapter.fetch(item)
                parsed = self._adapter.parse(raw, item)
                doc = self._adapter.normalize(parsed, topic_id=self._topic.id)
            except Exception as exc:  # noqa: BLE001 — 单条失败不中断整体
                result.errors.append(f"skip {item.url}: {exc}")
                continue
            if self._dedup.register(doc):
                self._jsonl.append(doc)
                docs.append(doc)
            else:
                result.documents_deduped += 1
        return docs

    def _persist(
        self,
        docs: list[NormalizedDocument],
        events: list[Event],
        observations: list[Observation],
    ) -> None:
        for doc in docs:
            self._sqlite.insert_document(doc)
        for company in self._topic.entities.companies:
            self._sqlite.insert_entity(
                company.canonical_name,
                company.canonical_name,
                company.aliases,
                topic_id=self._topic.id,
            )
        for event in events:
            self._sqlite.insert_event(event)
        for obs in observations:
            self._sqlite.insert_observation(obs)


def _final_status(result: RunResult) -> str:
    if not result.errors:
        return "success"
    if result.documents_collected or result.events_created or result.observations_extracted:
        return "partial"
    return "failed"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
