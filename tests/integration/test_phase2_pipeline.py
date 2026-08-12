"""Phase 2 Pipeline 整合测试：mock LLM，端到端全离线。

用真实 RSSAdapter 读取 file:// fixture + 脚本化 LLM Provider，
验证 采集 → 实体 → 分类 → 聚类 → 观测 → SQLite 持久化全链路。
"""

from __future__ import annotations

from industry_intelligence.collectors import SearchPlanner
from industry_intelligence.config.models import StorageConfig, SystemConfig
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


class ScriptedProvider(LLMProvider):
    """按 prompt 内容返回分类或观测结果；可注入异常。"""

    def __init__(
        self,
        event_type: str = "financing",
        observations: list[dict[str, object]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._event_type = event_type
        self._observations = observations if observations is not None else []
        self._exc = exc
        self.structured_calls = 0

    def generate(self, prompt: str) -> str:
        return "ok"

    def generate_structured(
        self, prompt: str, json_schema: dict[str, object]
    ) -> dict[str, object]:
        self.structured_calls += 1
        if self._exc is not None:
            raise self._exc
        if "允许的指标" in prompt:
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
    pipeline = Pipeline(
        topic=sample_topic,
        task=sample_task,
        system_config=SystemConfig(
            storage=StorageConfig(push_log_path=str(tmp_path / "push_log.jsonl"))
        ),
        adapter=adapter,
        jsonl_store=jsonl,
        sqlite_store=sqlite,
        entity_resolver=resolver,
        event_classifier=classifier,
        observation_extractor=extractor,
        planner=SearchPlanner(),
        event_clusterer=EventClusterer(),
    )
    return pipeline, sqlite


def test_full_chain(tmp_path, rss_fixture, sample_topic, sample_task) -> None:
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    assert result.status == "success"
    assert result.documents_collected == 5
    assert result.documents_deduped == 0
    assert result.events_created == 5
    # 仅命中了实体的文档（第 2/3/5 条）才触发观测抽取
    assert result.observations_extracted == 3
    assert result.errors == []

    assert len(sqlite.query_events("t1")) == 5
    assert len(sqlite.query_observations("t1")) == 3
    docs = sqlite._conn.execute("SELECT * FROM documents").fetchall()
    assert len(docs) == 5
    run_row = sqlite._conn.execute("SELECT * FROM runs").fetchone()
    assert run_row["status"] == "success"
    assert run_row["topic_id"] == "t1"


def test_llm_error_falls_back_to_keywords(tmp_path, rss_fixture, sample_topic, sample_task) -> None:
    provider = ScriptedProvider(exc=LLMError("boom"))
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    # LLMError 被分类器/抽取器内部吞掉：关键词回落分类，观测为空，整体仍成功
    assert result.status == "success"
    assert result.documents_collected == 5
    assert result.events_created == 5
    assert result.observations_extracted == 0
    assert result.errors == []
    # 关键词回落：第 3 条含"招标" → bid_order
    types = {row["event_type_id"] for row in sqlite.query_events("t1")}
    assert "bid_order" in types


def test_step_failure_does_not_abort(tmp_path, rss_fixture, sample_topic, sample_task) -> None:
    provider = ScriptedProvider(exc=RuntimeError("network"))
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    assert result.documents_collected == 5
    assert result.status == "partial"
    assert any("event classify" in e for e in result.errors)
    assert any("observation extraction" in e for e in result.errors)
    # 文档仍全部持久化，聚类仍执行
    assert len(sqlite._conn.execute("SELECT * FROM documents").fetchall()) == 5
    assert len(sqlite.query_events("t1")) == 5


def test_empty_collection(tmp_path, sample_topic, sample_task) -> None:
    provider = ScriptedProvider()
    adapter = RSSAdapter({})
    jsonl = JSONLStore(tmp_path / "empty.jsonl")
    sqlite = SQLiteStore(":memory:")
    pipeline = Pipeline(
        topic=sample_topic,
        task=sample_task,
        system_config=SystemConfig(
            storage=StorageConfig(push_log_path=str(tmp_path / "push_log.jsonl"))
        ),
        adapter=adapter,
        jsonl_store=jsonl,
        sqlite_store=sqlite,
        entity_resolver=EntityResolver(sample_topic),
        event_classifier=EventClassifier(
            provider=provider, event_types=EVENT_TYPES, keywords=[]
        ),
        observation_extractor=ObservationExtractor(provider=provider),
    )

    result = pipeline.run()

    assert result.status == "success"
    assert result.documents_collected == 0
    assert result.events_created == 0
    run_row = sqlite._conn.execute("SELECT * FROM runs").fetchone()
    assert run_row is not None
    assert run_row["status"] == "success"
