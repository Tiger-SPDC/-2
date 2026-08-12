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


def test_entity_changes_five_lines_with_filler() -> None:
    """三、企业竞争变化：5 家跟踪企业输出 5 条，无动态的以"暂无动态"补足。"""
    companies = [{"name": n} for n in
                 ("特来电", "星星充电", "国家电网", "南方电网", "云快充")]
    text = DigestFormatter().render(_bundle(companies=companies))
    section = text.split("三、企业竞争变化")[1]
    lines = [
        line for line in section.splitlines() if line.startswith("- ")
    ]
    assert len(lines) == 5
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert "本期暂无动态" in section
    assert section.count("本期暂无动态") == 4


def test_entity_changes_claim_preferred_over_event() -> None:
    """同一实体同时有主张与事件时，优先展示分析主张。"""
    event = {
        "event_id": "e1", "event_type_id": "other", "title": "特来电新站开业",
        "event_date": "2026-01-06", "summary": "s", "entity_ids": ["特来电"],
        "confidence": 1.0, "document_ids": [],
    }
    text = DigestFormatter().render(_bundle(events=[event]))
    section = text.split("三、企业竞争变化")[1]
    assert "- 特来电：[事实] 特来电发布液冷超充新品" in section
    assert "[事件] 特来电新站开业" not in section


def test_entity_changes_includes_non_tracked_event_entity() -> None:
    """事件中出现但未跟踪的企业也纳入动态，排在跟踪企业之后、暂无动态之前。"""
    event = {
        "event_id": "e1", "event_type_id": "other", "title": "蔚来发布超充网络计划",
        "event_date": "2026-01-06", "summary": "s", "entity_ids": ["蔚来"],
        "confidence": 1.0, "document_ids": [],
    }
    companies = [{"name": n} for n in ("特来电", "星星充电", "国家电网", "南方电网", "云快充")]
    text = DigestFormatter().render(_bundle(events=[event], companies=companies))
    section = text.split("三、企业竞争变化")[1]
    lines = [
        line for line in section.splitlines() if line.startswith("- ")
    ]
    assert len(lines) == 5
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert "- 蔚来：[事件] 蔚来发布超充网络计划" in lines
    # 未跟踪实体占一位后，暂无动态应少一位（4 - 1 = 3）
    assert section.count("本期暂无动态") == 3
