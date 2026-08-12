"""采集相关性门控单元测试：RSS/官方站点放行、websearch 按主题信号过滤（全离线）。"""

from __future__ import annotations

from unittest.mock import Mock

from industry_intelligence.config.models import SystemConfig
from industry_intelligence.controller.pipeline import Pipeline, RunResult
from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.sources.models import (
    ParsedDocument,
    QueryPlan,
    RawContent,
    SourceItem,
)
from industry_intelligence.storage.jsonl_store import JSONLStore
from industry_intelligence.storage.sqlite_store import SQLiteStore
from industry_intelligence.utils.relevance import (
    build_relevance_terms,
    is_doc_relevant,
)

TERMS = ["充电桩", "特来电", "星星充电"]


def _build_doc(source_id: str, title: str, content: str = "", **extra) -> NormalizedDocument:
    return NormalizedDocument(
        document_id=source_id.replace(":", "-"),
        canonical_url=f"https://example.com/{title}",
        source_id=source_id,
        title=title,
        content_text=content,
        content_hash="c",
        url_hash="u",
        source_grade="C",
        topic_id="t1",
        extra=extra,
    )


def test_rss_passes_regardless_of_content() -> None:
    doc = _build_doc("rss:demo", "Brisbane Story Bridge Climb", "unrelated")
    assert is_doc_relevant(doc, TERMS) is True


def test_websearch_junk_rejected() -> None:
    doc = _build_doc("websearch:bing", "Brisbane Story Bridge Climb", "unrelated")
    assert is_doc_relevant(doc, TERMS) is False


def test_websearch_relevant_kept() -> None:
    doc = _build_doc("websearch:bing", "特来电推出液冷超充新品")
    assert is_doc_relevant(doc, TERMS) is True


def test_websearch_official_domain_kept() -> None:
    # site: 官方域查询按构造可信，内容无需命中主题信号
    doc = _build_doc("websearch:bing", "每日新闻速览", official_domain="gov.cn")
    assert is_doc_relevant(doc, TERMS) is True


def test_empty_terms_passes_everything() -> None:
    doc = _build_doc("websearch:bing", "anything", "content")
    assert is_doc_relevant(doc, []) is True


class _StubPlanner:
    def __init__(self, plans: list[QueryPlan]) -> None:
        self._plans = plans

    def generate_plans(self, topic, task) -> list[QueryPlan]:  # noqa: ANN001
        return self._plans


class _StubAdapter:
    source_id = "stub"
    source_grade = "C"

    def __init__(self, items: list[SourceItem]) -> None:
        self._items = items

    def discover(self, queries, context) -> list[SourceItem]:  # noqa: ANN001
        return self._items

    def fetch(self, item: SourceItem) -> RawContent:
        return RawContent(item_id=item.item_id, url=item.url)

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        return ParsedDocument(
            url=item.url,
            item_id=item.item_id,
            source_id=item.source_id,
            title=item.title or "",
            content_text=str(item.extra.get("snippet", "")),
            raw_type="html",
            extra=dict(item.extra),
        )

    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        return NormalizedDocument(
            document_id=parsed.item_id,
            canonical_url=parsed.url,
            source_id=parsed.source_id,
            title=parsed.title,
            content_text=parsed.content_text,
            content_hash=parsed.item_id,
            url_hash=parsed.item_id,
            source_grade="C",
            topic_id=topic_id,
            extra=dict(parsed.extra),
        )

    def health_check(self) -> bool:
        return True


def _item(sid: str, iid: str, title: str, **extra) -> SourceItem:
    return SourceItem(
        url=f"https://example.com/{iid}",
        item_id=iid,
        source_id=sid,
        title=title,
        extra=extra,
    )


def _make_pipeline(tmp_path, adapter, planner, sqlite, topic, task) -> Pipeline:  # noqa: ANN001
    return Pipeline(
        topic=topic,
        task=task,
        system_config=SystemConfig(),
        adapter=adapter,
        jsonl_store=JSONLStore(tmp_path / "collection.jsonl"),
        sqlite_store=sqlite,
        entity_resolver=Mock(),
        event_classifier=Mock(),
        observation_extractor=Mock(),
        planner=planner,
    )


def test_collect_gates_websearch_junk(tmp_path, sample_topic, sample_task) -> None:  # noqa: ANN001
    sqlite = SQLiteStore(":memory:")
    adapter = _StubAdapter([
        _item("websearch:bing", "j1", "Brisbane Story Bridge Climb"),
        _item("websearch:bing", "r1", "特来电推出液冷超充"),
        _item("websearch:bing", "o1", "官方站点每日新闻", official_domain="gov.cn"),
        _item("rss:demo", "d1", "Foreign unrelated headline"),
    ])
    planner = _StubPlanner([QueryPlan(query_id="q1", query_string="充电桩")])
    pipeline = _make_pipeline(tmp_path, adapter, planner, sqlite, sample_topic, sample_task)

    result = RunResult(run_id="test")
    docs = pipeline._collect(result)
    # 仅垃圾 websearch 被过滤；相关/官方/RSS 全部保留
    assert result.documents_filtered == 1
    assert {d.document_id for d in docs} == {"r1", "o1", "d1"}


def test_collect_purges_legacy_junk(tmp_path, sample_topic, sample_task, make_doc) -> None:  # noqa: ANN001
    sqlite = SQLiteStore(":memory:")
    sqlite.insert_document(
        make_doc(document_id="j0", source_id="websearch:bing",
                 title="Brisbane Story Bridge Climb", content_text="unrelated")
    )
    adapter = _StubAdapter([_item("rss:demo", "d1", "标题")])
    planner = _StubPlanner([QueryPlan(query_id="q1", query_string="充电桩")])
    pipeline = _make_pipeline(tmp_path, adapter, planner, sqlite, sample_topic, sample_task)

    result = RunResult(run_id="test")
    docs = pipeline._collect(result)
    # 历史垃圾在采集前被清理（documents_filtered 计入），新 RSS 保留
    assert result.documents_filtered == 1
    assert {d.document_id for d in docs} == {"d1"}
    assert "j0" not in {r["document_id"] for r in
                        sqlite._conn.execute("SELECT document_id FROM documents").fetchall()}


def test_terms_from_topic(sample_topic) -> None:  # noqa: ANN001
    terms = build_relevance_terms(sample_topic)
    assert "充电桩" in terms
    assert "充电基础设施" in terms
    assert "特来电新能源" in terms
