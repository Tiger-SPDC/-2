"""Phase 4 Pipeline 集成测试：mock LLM，端到端全离线。

真实 RSSAdapter 读取 file:// fixture + 脚本化 LLM Provider，验证
Phase 1(采集) + Phase 2(实体/事件/观测) + Phase 3(竞争情报分析)
+ Phase 4(审查/报告/通知) 全链路。审查 claim_id 从 review prompt 解析，
报告写入 tmp_path，通知用内存假 Adapter。
"""

from __future__ import annotations

import re

from industry_intelligence.analysis.engine import AnalysisEngine
from industry_intelligence.analysis.models import (
    TREND_INDICATORS,
)
from industry_intelligence.analysis.review import ReviewAgent
from industry_intelligence.collectors import SearchPlanner
from industry_intelligence.config.models import SystemConfig
from industry_intelligence.controller import Pipeline
from industry_intelligence.entities import EntityResolver
from industry_intelligence.intelligence import EventClassifier, EventClusterer
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.metrics import ObservationExtractor
from industry_intelligence.notification.adapter import (
    NotificationAdapter,
    NotificationResult,
)
from industry_intelligence.reporting.engine import ReportEngine
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
    """按 JSON Schema 分发：分类 / 观测 / 分析 Claim / 审查；可注入异常。"""

    def __init__(
        self,
        event_type: str = "new_product",
        observations: list[dict[str, object]] | None = None,
        claims: list[dict[str, object]] | None = None,
        analysis_exc: Exception | None = None,
        review_exc: Exception | None = None,
    ) -> None:
        self._event_type = event_type
        self._observations = observations if observations is not None else []
        self._claims = claims if claims is not None else ANALYSIS_CLAIMS
        self._analysis_exc = analysis_exc
        self._review_exc = review_exc
        self.structured_calls = 0

    def generate(self, prompt: str) -> str:
        return "ok"

    def generate_structured(
        self, prompt: str, json_schema: dict[str, object]
    ) -> dict[str, object]:
        self.structured_calls += 1
        props = json_schema.get("properties", {})
        if "reviews" in props:
            if self._review_exc is not None:
                raise self._review_exc
            ids = re.findall(r"claim_id: (\S+)", prompt)
            return {
                "reviews": [
                    {"claim_id": cid, "verdict": "pass", "reason": "ok"}
                    for cid in ids
                ]
            }
        if "claims" in props:
            if self._analysis_exc is not None:
                raise self._analysis_exc
            return {"claims": self._claims}
        if "observations" in props:
            return {"observations": self._observations}
        return {"event_type_id": self._event_type, "reason": "reason"}


class FakeNotifier(NotificationAdapter):
    """内存通知 Adapter：记录发送，始终成功。"""

    channel_name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, content: str) -> NotificationResult:
        self.sent.append((title, content))
        return NotificationResult(success=True, retry_count=1)


def _build_pipeline(tmp_path, rss_fixture, sample_topic, sample_task, provider,
                    notifier=None):
    adapter = RSSAdapter({"demo": rss_fixture.as_uri()}, max_entries=50)
    jsonl = JSONLStore(tmp_path / "collection.jsonl")
    sqlite = SQLiteStore(":memory:")
    engine = AnalysisEngine(
        provider=provider,
        sqlite_store=sqlite,
        topic=sample_topic,
        task=sample_task,
        prompts={},
    )
    review_agent = ReviewAgent(
        provider=provider,
        sqlite_store=sqlite,
        prompt_template="review template",
        topic=sample_topic,
        task=sample_task,
    )
    report_engine = ReportEngine(
        sqlite_store=sqlite,
        topic=sample_topic,
        task=sample_task,
        output_dir=tmp_path / "reports",
    )
    pipeline = Pipeline(
        topic=sample_topic,
        task=sample_task,
        system_config=SystemConfig(),
        adapter=adapter,
        jsonl_store=jsonl,
        sqlite_store=sqlite,
        entity_resolver=EntityResolver(sample_topic),
        event_classifier=EventClassifier(
            provider=provider,
            event_types=EVENT_TYPES,
            keywords=sample_topic.keywords.events,
        ),
        observation_extractor=ObservationExtractor(provider=provider),
        planner=SearchPlanner(),
        event_clusterer=EventClusterer(),
        analysis_engine=engine,
        review_agent=review_agent,
        report_engine=report_engine,
        notification_adapter=notifier,
    )
    return pipeline, sqlite


def test_full_chain_with_phase4(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    notifier = FakeNotifier()
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider, notifier
    )

    result = pipeline.run()

    # Phase 1 + 2 + 3 结果
    assert result.status == "success"
    assert result.documents_collected == 5
    assert result.events_created == 5
    assert result.analysis_claims == 4
    assert result.evidence_coverage == 1.0
    assert set(result.trends.keys()) == TREND_INDICATORS

    # Phase 4 审查：4 条 claim 全部通过
    assert result.review_passed == 4
    assert result.review_rejected == 0
    assert result.review_downgraded == 0
    rows = sqlite.query_claim_reviews(result.run_id)
    assert len(rows) == 4
    assert {r["verdict"] for r in rows} == {"pass"}

    # Phase 4 报告：三种格式落盘 + 摘要文本
    assert result.report_paths
    for key in ("markdown", "excel", "digest"):
        assert result.report_paths.get(key)
    assert result.digest_text
    run_dir = tmp_path / "reports" / result.run_id
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "report.xlsx").is_file()
    assert (run_dir / "digest.txt").is_file()

    # Phase 4 通知：摘要已推送
    assert result.notification_sent is True
    assert len(notifier.sent) == 1
    assert notifier.sent[0][0].startswith("产业竞争情报周报")


def test_phase4_optional_backward_compat(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    # 不注入 review/report/notification → 行为与 Phase 3 完全一致
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    pipeline, sqlite = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )
    # 移除 Phase 4 组件
    pipeline._review_agent = None
    pipeline._report_engine = None
    pipeline._notification_adapter = None

    result = pipeline.run()

    assert result.analysis_claims == 4
    assert result.review_passed == 0
    assert result.report_paths == {}
    assert result.digest_text == ""
    assert result.notification_sent is False
    assert sqlite.query_claim_reviews(result.run_id) == []


def test_review_failure_does_not_block_reports(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    provider = ScriptedProvider(
        event_type="new_product",
        observations=SAMPLE_OBS,
        review_exc=LLMError("review boom"),
    )
    pipeline, _ = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, sample_task, provider
    )

    result = pipeline.run()

    # 审查失败被记录，报告照常生成，整体仍 partial
    assert result.review_passed == 0
    assert any("review boom" in e for e in result.errors)
    assert result.report_paths.get("markdown")
    assert result.status == "partial"


def test_notify_gate_respects_output_notify_false(
    tmp_path, rss_fixture, sample_topic, sample_task
) -> None:
    # Phase 5：task.output.notify=False 时不推送，但报告照常生成
    import dataclasses

    from industry_intelligence.config.models import TaskOutput

    task = dataclasses.replace(sample_task, output=TaskOutput(notify=False))
    provider = ScriptedProvider(event_type="new_product", observations=SAMPLE_OBS)
    notifier = FakeNotifier()
    pipeline, _ = _build_pipeline(
        tmp_path, rss_fixture, sample_topic, task, provider, notifier
    )

    result = pipeline.run()

    assert result.status == "success"
    assert result.notification_sent is False
    assert notifier.sent == []
    assert result.report_paths.get("markdown")  # 报告不受 notify 影响
