"""Phase 3 Pipeline 集成测试：mock LLM，端到端全离线。

真实 RSSAdapter 读取 file:// fixture + 脚本化 LLM Provider，验证
Phase 1(采集) + Phase 2(实体/事件/观测) + Phase 3(竞争情报分析) 全链路。
"""

from __future__ import annotations

from industry_intelligence.analysis.engine import AnalysisEngine
from industry_intelligence.analysis.models import (
    ANALYSIS_COMPETITOR,
    ANALYSIS_MARKET,
    ANALYSIS_RISK,
    ANALYSIS_TECHNOLOGY,
    TREND_INDICATORS,
)
from industry_intelligence.collectors import SearchPlanner
from industry_intelligence.config.models import SystemConfig
from industry_intelligence.controller import Pipeline
from industry_intelligence.entities import EntityResolver
from industry_intelligence.intelligence import EventClassifier, EventClusterer
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.metrics import ObservationExtractor
from industry_intelligence.sources import RSSAdapter
from industry_intelligence.storage import JSONLStore, SQLiteStore

EVENT_TYPES = {
    "policy_regulation": "政策与监管",
    "bid_order": "中标/订单",
    "financing": "融资",
    "new_product": "新产品",
    "other": "其他",
}

SAMPLE_OBS = [
    {
        "metric_id": "station_count",
        "entity_id": "特来电",
        "value": 100.0,
        "unit": "座",
        "confidence": 0.9,
        "evidence_text": "测试证据",
    }
]

# 分析师返回的 Claim（证据 ID 留空，交由分析师用窗口真实文档兜底）
ANALYSIS_CLAIMS = [
    {
        "claim_text": "特来电发布液冷超充新品，技术热度与竞争活动上升",
        "claim_type": "fact",
        "confidence": 0.9,
        "entity_id": "特来电",
        "evidence_document_ids": [],
        "evidence_observation_ids": [],
    }
]


class ScriptedProvider(LLMProvider):
    """按 JSON Schema 分发：分类 / 观测 / 分析 Claim；可注入异常。"""

    def __init__(
        self,
        event_type: str = "new_product",
        observations: list[dict[str, object]] | None = None,
        claims: list[dict[str, object]] | None = None,
        analysis_exc: Exception | None = None,
    ) -> None:
        self._event_type = event_type
        self._observations = observations if observations is not None else []
        self._claims = claims if claims is not None else ANALYSIS_CLAIMS
        self._analysis_exc = analysis_exc
        self.structured_calls = 0

    def generate(self, prompt: str) -> str:
        return "ok"

    def generate_structured(
        self, prompt: str, json_schema: dict[str, object]
    ) -> dict[str, object]:
        self.structured_calls += 1
        props = json_schema.get("properties", {})
        if "claims" in props:
            if self._analysis_exc is not None:
                raise self._analysis_exc
            return {"claims": self._claims}
        if "observations" in props:
            return {"observations": self._observations}
        return {"event_type_id": self._event_type, "reason": "reason"}


def _build_pipeline(tmp_path, rss_fixture, sample_topic, sample_task, provider):
    adapter = RSSAdapter({"demo": rss_fixture.as_uri()}, max_entries=50)
    jsonl = JSONLStore(tmp_path / "collection.jsonl")
    sqlite = SQLiteStore(":memory:")
    resolver = EntityResolver(sample_topic)
    classifier = EventClassifier(
        provider=provider,
        event_types=EVENT_TYPES,
        keywords=sample_topic.keywords.events,
    )
    extractor = ObservationExtractor(provider=provider)
    engine = AnalysisEngine(
        provider=provider,
        sqlite_store=sqlite,
        topic=sample_topic,
        task=sample_task,
        prompts={},
    )
    pipeline = Pipeline(
        topic=sample_topic,
        task=sample_task,
        system_config=SystemConfig(),
        adapter=adapter,
        jsonl_store=jsonl,
        sqlite_store=sqlite,
        entity_resolver=resolver,
        event_classifier=classifier,
        observation_extractor=extractor,
        planner=SearchPlanner(),
        event_clusterer=EventClusterer(),
        analysis_engine=engine,
    )
    return pipeline, sqlite


def test_full_chain_with_phase3(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    # Phase 1 + 2 结果与无分析时一致
    assert result.status == "success"
    assert result.documents_collected == 5
    assert result.events_created == 5
    assert result.observations_extracted == 3
    assert result.errors == []

    # Phase 3：4 维度各 1 条 Claim，均有证据 → 覆盖率 100%
    assert len(result.analysis_results) == 4
    assert {r.analysis_type for r in result.analysis_results} == {
        ANALYSIS_COMPETITOR, ANALYSIS_MARKET,
        ANALYSIS_TECHNOLOGY, ANALYSIS_RISK,
    }
    assert result.analysis_claims == 4
    assert result.evidence_coverage == 1.0
    assert set(result.trends.keys()) == TREND_INDICATORS

    # Claim 与证据已持久化到 SQLite
    rows = sqlite.query_claims(result.run_id)
    assert len(rows) == 4
    for row in rows:
        assert sqlite.query_claim_evidence(row["claim_id"])
    run_row = sqlite._conn.execute("SELECT * FROM runs").fetchone()
    assert run_row["analysis_claims"] == 4
    assert run_row["evidence_coverage"] == 1.0


def test_no_engine_skips_analysis_backward_compat(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    adapter = RSSAdapter({"demo": rss_fixture.as_uri()}, max_entries=50)
    jsonl = JSONLStore(tmp_path / "collection.jsonl")
    sqlite = SQLiteStore(":memory:")
    pipeline = Pipeline(
        topic=sample_topic,
        task=sample_task,
        system_config=SystemConfig(),
        adapter=adapter,
        jsonl_store=jsonl,
        sqlite_store=sqlite,
        entity_resolver=EntityResolver(sample_topic),
        event_classifier=EventClassifier(
            provider=provider, event_types=EVENT_TYPES,
            keywords=sample_topic.keywords.events,
        ),
        observation_extractor=ObservationExtractor(provider=provider),
        planner=SearchPlanner(),
        event_clusterer=EventClusterer(),
        analysis_engine=None,
    )

    result = pipeline.run()

    # 无分析引擎 → 行为与 Phase 2 完全一致
    assert result.status == "success"
    assert result.analysis_results == []
    assert result.analysis_claims == 0
    assert result.evidence_coverage == 0.0
    assert result.trends == {}
    assert sqlite.query_claims(result.run_id) == []


def test_analysis_llm_failure_degrades_gracefully(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    provider = ScriptedProvider(
        event_type="new_product",
        observations=SAMPLE_OBS,
        analysis_exc=LLMError("analysis boom"),
    )
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    # 采集/分析照常；分析阶段 LLM 失败被记录，不中断整体
    assert result.documents_collected == 5
    assert result.events_created == 5
    assert result.analysis_claims == 0
    assert result.evidence_coverage == 0.0
    assert result.status == "partial"
    assert any("analysis boom" in e for e in result.errors)
    # 分析错误（errors 非空）→ status partial；文档仍持久化
    assert len(sqlite._conn.execute("SELECT * FROM documents").fetchall()) == 5
