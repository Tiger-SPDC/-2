"""ReportEngine 单元测试：文件写入、开关控制、失败隔离（全离线）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from industry_intelligence.config.models import ReportConfig
from industry_intelligence.reporting.engine import (
    FORMAT_DIGEST,
    FORMAT_EXCEL,
    FORMAT_MARKDOWN,
    ReportEngine,
)
from industry_intelligence.storage import SQLiteStore

NOW = datetime.now(UTC)
T1 = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
TODAY = NOW.isoformat(timespec="seconds")


def _seed_store(make_doc) -> SQLiteStore:
    store = SQLiteStore(":memory:")
    store.insert_run("r1", "t1", "tk1", T1)
    store.insert_document(
        make_doc(document_id="d1", title="文档一", fetched_at=TODAY)
    )
    store.insert_claim(
        claim_id="c1", claim_text="结论一", claim_type="fact",
        confidence=0.9, analysis_type="market", topic_id="t1",
        run_id="r1", entity_id="特来电",
    )
    store.insert_claim_evidence("c1", document_id="d1", evidence_role="primary_source")
    store.insert_claim_review("rv1", "c1", "pass", "r1", reason="ok")
    return store


def _engine(store, sample_topic, sample_task, config=None, output_dir="output/reports"):
    return ReportEngine(
        store, sample_topic, sample_task,
        report_config=config, output_dir=output_dir,
    )


def test_run_writes_all_formats(
    make_doc, sample_topic, sample_task, tmp_path
) -> None:
    store = _seed_store(make_doc)
    engine = _engine(store, sample_topic, sample_task, output_dir=tmp_path)
    result = engine.run("r1", analysis_claims=1, evidence_coverage=1.0)

    assert result.errors == []
    assert FORMAT_MARKDOWN in result.paths
    assert FORMAT_EXCEL in result.paths
    assert FORMAT_DIGEST in result.paths
    run_dir = tmp_path / "r1"
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "report.xlsx").is_file()
    assert (run_dir / "digest.txt").is_file()
    assert result.digest_text  # 摘要文本返回给通知层


def test_config_switches_control_formats(
    make_doc, sample_topic, sample_task, tmp_path
) -> None:
    store = _seed_store(make_doc)
    config = ReportConfig(markdown=True, excel=False, wechat_digest=False)
    result = _engine(store, sample_topic, sample_task, config, tmp_path).run("r1")
    assert FORMAT_MARKDOWN in result.paths
    assert FORMAT_EXCEL not in result.paths
    assert FORMAT_DIGEST not in result.paths
    assert result.digest_text == ""


def test_markdown_failure_does_not_block_excel(
    make_doc, sample_topic, sample_task, tmp_path
) -> None:
    store = _seed_store(make_doc)
    engine = _engine(store, sample_topic, sample_task, output_dir=tmp_path)
    with mock.patch(
        "industry_intelligence.reporting.formatters.markdown.MarkdownFormatter.render",
        side_effect=RuntimeError("md boom"),
    ):
        result = engine.run("r1")
    assert any("report markdown" in e and "md boom" in e for e in result.errors)
    assert FORMAT_MARKDOWN not in result.paths
    assert FORMAT_EXCEL in result.paths  # Excel 照常生成
    assert (tmp_path / "r1" / "report.xlsx").is_file()


def test_missing_run_still_writes_empty_reports(
    make_doc, sample_topic, sample_task, tmp_path
) -> None:
    store = SQLiteStore(":memory:")
    result = _engine(store, sample_topic, sample_task, output_dir=tmp_path).run("r0")
    assert result.errors == []
    assert (tmp_path / "r0" / "report.md").is_file()
