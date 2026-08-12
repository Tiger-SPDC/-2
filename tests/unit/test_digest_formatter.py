"""DigestFormatter 单元测试：3 节结构、字数上限、质量等级（全离线）。"""

from __future__ import annotations

from industry_intelligence.reporting.builder import ReportDataBundle
from industry_intelligence.reporting.formatters.digest import (
    _MAX_CHARS,
    DigestFormatter,
)

_CLAIM = {
    "claim_id": "c1",
    "claim_text": "特来电发布液冷超充新品，市场热度显著上升",
    "claim_type": "fact",
    "confidence": 0.9,
    "entity_id": "特来电",
    "analysis_type": "technology",
}


def _bundle(**overrides) -> ReportDataBundle:
    kwargs: dict[str, object] = dict(
        run_id="r1",
        topic_id="t1",
        task_id="tk1",
        status="success",
        period_start="2026-01-01",
        period_end="2026-01-08",
        claims=[_CLAIM],
        quality={
            "document_count": 5.0,
            "event_count": 3.0,
            "claim_count": 1.0,
            "evidence_coverage": 1.0,
            "review_reject_rate": 0.0,
        },
    )
    kwargs.update(overrides)
    return ReportDataBundle(**kwargs)


def test_render_contains_three_sections() -> None:
    text = DigestFormatter().render(_bundle())
    for title in (
        "一、本周一句话判断",
        "二、最重要的 5 件事",
        "三、企业竞争变化",
    ):
        assert title in text
    # 冗余节已按需求移除
    assert "四、关键数据" not in text
    assert "五、风险/机会" not in text
    assert "六、需要继续跟踪" not in text


def test_quality_level_high() -> None:
    text = DigestFormatter().render(_bundle())
    assert "数据质量：High" in text


def test_quality_level_medium() -> None:
    text = DigestFormatter().render(
        _bundle(quality={
            "document_count": 5.0, "evidence_coverage": 0.6,
            "review_reject_rate": 0.5,
        })
    )
    assert "数据质量：Medium" in text


def test_report_path_appended() -> None:
    text = DigestFormatter().render(_bundle(), report_path="output/r1/report.md")
    assert "完整报告：output/r1/report.md" in text


def test_long_text_truncated() -> None:
    long_claim = {"claim_id": "c1", "claim_text": "长" * 500,
                  "claim_type": "fact", "confidence": 0.9,
                  "entity_id": "特来电", "analysis_type": "technology"}
    text = DigestFormatter().render(
        _bundle(claims=[long_claim]), report_path="output/r1/report.md"
    )
    assert "已截断" in text
    # 总长（含标点）严格不超过上限
    assert len(text) <= _MAX_CHARS
    # 超长时只截正文，报告链接必须保留
    assert "完整报告：output/r1/report.md" in text
