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


def test_hot_topics_line_rendered_when_present() -> None:
    """有 LLM 热点时，摘要顶部出现"本期热点关注"行。"""
    text = DigestFormatter().render(
        _bundle(hot_topics=["液冷超充", "V2G 车网互动", "光储充一体化"])
    )
    assert "本期热点关注：液冷超充、V2G 车网互动、光储充一体化" in text


def test_hot_topics_line_omitted_when_empty() -> None:
    """无热点时无热点行，摘要仍为 3 节结构。"""
    text = DigestFormatter().render(_bundle())
    assert "本期热点关注" not in text
    assert "一、本周一句话判断" in text


def test_top5_prioritizes_hot_matching_event() -> None:
    """5 件事按热点命中优先排序，再按日期。"""
    events = [
        {"event_id": "e_other", "event_type_id": "t", "title": "普通充电新闻",
         "event_date": "2026-01-08", "summary": "无关内容", "confidence": 1.0},
        {"event_id": "e_hot", "event_type_id": "t", "title": "液冷超充站落地北京",
         "event_date": "2026-01-06", "summary": "液冷超充 光储充一体化", "confidence": 1.0},
    ]
    text = DigestFormatter().render(
        _bundle(events=events, hot_topics=["液冷超充"])
    )
    section = text.split("二、最重要的 5 件事")[1].split("三、企业竞争变化")[0]
    assert section.index("液冷超充站落地北京") < section.index("普通充电新闻")


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


def test_entity_changes_fills_up_to_min_when_sparse() -> None:
    """三、企业竞争变化：内容优先——只有 1 家有动态时，暂无动态只补到最小条数。"""
    companies = [{"name": n} for n in
                 ("特来电", "星星充电", "国家电网", "南方电网", "云快充")]
    text = DigestFormatter().render(_bundle(companies=companies))
    section = text.split("三、企业竞争变化")[1]
    lines = [
        line for line in section.splitlines() if line.startswith("- ")
    ]
    assert len(lines) == 3
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert section.count("本期暂无动态") == 2


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
    assert len(lines) == 3
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert "- 蔚来：[事件] 蔚来发布超充网络计划" in lines
    # 有动态的有 2 家（特来电、蔚来），暂无动态只补到 3 条最小数（1 条）
    assert section.count("本期暂无动态") == 1


def test_entity_changes_includes_non_tracked_claim_entity() -> None:
    """主张（claim）中出现但未跟踪的企业也纳入动态——比亚迪/蔚来等应上屏。"""
    claims = [
        {"claim_id": "c1", "claim_text": "特来电发布液冷超充新品，市场热度显著上升",
         "claim_type": "fact", "confidence": 0.9, "entity_id": "特来电",
         "analysis_type": "technology"},
        {"claim_id": "c2", "claim_text": "比亚迪闪充技术落地 30%→80% 只需 10 分钟",
         "claim_type": "fact", "confidence": 0.85, "entity_id": "比亚迪",
         "analysis_type": "technology"},
    ]
    companies = [{"name": n} for n in ("特来电", "国家电网", "云快充")]
    text = DigestFormatter().render(_bundle(claims=claims, companies=companies))
    section = text.split("三、企业竞争变化")[1]
    lines = [
        line for line in section.splitlines() if line.startswith("- ")
    ]
    # 有动态的有 2 家（特来电、比亚迪），排在前面；暂无动态只补到 3 条最小数
    assert any(line.startswith("- 比亚迪：[事实] 比亚迪闪充技术落地") for line in lines)
    assert lines[1].startswith("- 比亚迪：")
    assert section.count("本期暂无动态") == 1
    assert len(lines) == 3
