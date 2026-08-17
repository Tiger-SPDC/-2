"""DigestFormatter 单元测试：3 节结构、字数上限、质量等级（全离线）。"""

from __future__ import annotations

from industry_intelligence.reporting.builder import ReportDataBundle
from industry_intelligence.reporting.formatters.digest import (
    _MAX_CHARS,
    DigestFormatter,
    _filter_events,
    _truncate,
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
        "二、最重要的",
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
    section = text.split("二、最重要的")[1].split("三、企业竞争变化")[0]
    assert section.index("液冷超充站落地北京") < section.index("普通充电新闻")


def test_long_text_truncated() -> None:
    """超长内容在分节内部被截断（省略号），总长 ≤600，报告链接保留。"""
    long_claim = {"claim_id": "c1", "claim_text": "长" * 500,
                  "claim_type": "fact", "confidence": 0.9,
                  "entity_id": "特来电", "analysis_type": "technology"}
    text = DigestFormatter().render(
        _bundle(claims=[long_claim]), report_path="output/r1/report.md"
    )
    # 分节截断产生省略号，总长（含标点）严格不超过上限
    assert "…" in text
    assert len(text) <= _MAX_CHARS
    # 超长时只截正文，报告链接必须保留
    assert "完整报告：output/r1/report.md" in text


def test_reduces_items_not_truncates_when_over_budget() -> None:
    """整体超预算时减条数（而非截半句）：条目完整、条数在 3~5、总长 ≤600。"""
    events = [
        {"event_id": f"e{i}", "event_type_id": "t", "title": f"标题{i}" + "字" * 40,
         "event_date": "2026-01-08", "summary": "s", "confidence": 1.0}
        for i in range(5)
    ]
    claims = [
        {"claim_id": f"c{i}", "claim_text": f"企业{i}动态" + "字" * 50,
         "claim_type": "fact", "confidence": 0.9, "entity_id": f"企业{i}",
         "analysis_type": "technology"}
        for i in range(5)
    ]
    text = DigestFormatter().render(
        _bundle(events=events, claims=claims), report_path="output/r1/report.md"
    )
    assert len(text) <= _MAX_CHARS
    assert "完整报告：output/r1/report.md" in text
    # 减条数已适配，无需 _fit 硬截断
    assert "已截断" not in text
    # 5 件事保留条数在 3~5
    top_label = text.split("二、最重要的 ")[1].split(" 件事")[0]
    assert top_label.isdigit() and 3 <= int(top_label) <= 5
    # 企业节保留条数在 3~5
    entity_lines = [
        line for line in text.split("三、企业竞争变化")[1].splitlines()
        if line.startswith("- ")
    ]
    assert 3 <= len(entity_lines) <= 5


def test_truncate_cuts_at_sentence_boundary() -> None:
    """语义截断：优先截到句号，不硬切半句；无边界时才加省略号且 ≤ max_len。"""
    # 句号位置靠后（>= max_len//2）→ 截到句号，不加省略号
    out = _truncate("甲" * 25 + "。" + "乙" * 100, 40)
    assert out == "甲" * 25 + "。"
    assert "…" not in out
    assert len(out) <= 40
    # 无句子边界 → 省略号，且结果不超 max_len
    out2 = _truncate("长" * 100, 30)
    assert out2.endswith("…")
    assert len(out2) <= 30


def test_fit_fallback_caps_and_marks() -> None:
    """_fit 兜底：正文极端超长时硬截并加「已截断」，总长 ≤ limit，footer 保留。"""
    body = "字" * 700
    footer = "\n数据质量：High"
    text = DigestFormatter()._fit(body, footer, limit=600)
    assert "已截断" in text
    assert len(text) <= 600
    assert footer in text


def test_entity_changes_no_placeholder_for_idle_companies() -> None:
    """企业节不再用"暂无动态"占位：只有真实动态的企业上屏。"""
    companies = [{"name": n} for n in
                 ("特来电", "星星充电", "国家电网", "南方电网", "云快充")]
    text = DigestFormatter().render(_bundle(companies=companies))
    section = text.split("三、企业竞争变化")[1]
    lines = [
        line for line in section.splitlines() if line.startswith("- ")
    ]
    assert len(lines) == 1
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert "本期暂无动态" not in text


def test_entity_claim_full_sentence_not_truncated() -> None:
    """企业节动态文案：正常长度完整句子（≤90 字）完整保留，不截半句。"""
    claim_text = (
        "浙江宁波一充电站发生车辆起火，极氪回应称涉事车辆曾严重碰撞且未官方维修，"
        "起火原因或与充电桩无关，但事件引发对充电安全的关注。"
    )
    claims = [{
        "claim_id": "c1", "claim_text": claim_text, "claim_type": "fact",
        "confidence": 0.9, "entity_id": "极氪", "analysis_type": "technology",
    }]
    text = DigestFormatter().render(_bundle(claims=claims))
    section = text.split("三、企业竞争变化")[1]
    assert claim_text in section  # 完整句子原样保留
    assert "…" not in section


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


def test_top5_filters_off_topic_and_navigation() -> None:
    """5 件事严格过滤：只留命中 core 且不命中 exclude 的事件。"""
    events = [
        {"event_id": "e1", "event_type_id": "t", "title": "某地充电站投用",
         "event_date": "2026-01-08", "summary": "s", "confidence": 1.0},
        {"event_id": "e2", "event_type_id": "t", "title": "五菱星光纯电值得等吗",
         "event_date": "2026-01-07", "summary": "s", "confidence": 1.0},
        {"event_id": "e3", "event_type_id": "t", "title": "华为 - 维基百科",
         "event_date": "2026-01-06", "summary": "s", "confidence": 1.0},
        {"event_id": "e4", "event_type_id": "t", "title": "7千瓦充电桩值得买吗",
         "event_date": "2026-01-05", "summary": "s", "confidence": 1.0},
    ]
    text = DigestFormatter().render(_bundle(
        events=events,
        focus_terms=["充电桩", "充电站", "储能"],
        exclude_terms=["值得买", "值得等", "维基百科"],
    ))
    section = text.split("二、最重要的")[1].split("三、企业竞争变化")[0]
    assert "某地充电站投用" in section          # 命中 core 且无 exclude → 保留
    assert "五菱星光纯电值得等吗" not in section  # 无 core 词 → 剔除
    assert "华为 - 维基百科" not in section      # 无 core 词 → 剔除
    assert "7千瓦充电桩值得买吗" not in section  # 命中 core 但含 exclude → 剔除


def test_filter_events_empty_terms_is_noop() -> None:
    """无 core/exclude 词表时不过滤（向后兼容），不误杀。"""
    events = [
        {"title": "充电站投用"},
        {"title": "普通汽车新闻"},
    ]
    assert _filter_events(events, [], []) == events
    # 仅 focus 词时按命中保留，仅 exclude 词时按命中剔除
    assert [e["title"] for e in _filter_events(events, ["充电站"], [])] == ["充电站投用"]
    assert [e["title"] for e in _filter_events(events, [], ["充电站"])] == ["普通汽车新闻"]


def test_entity_changes_includes_non_tracked_event_entity() -> None:
    """事件中出现但未跟踪的企业也上屏，无动态企业不占位。"""
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
    assert len(lines) == 2
    assert lines[0] == "- 特来电：[事实] 特来电发布液冷超充新品，市场热度显著上升"
    assert "- 蔚来：[事件] 蔚来发布超充网络计划" in lines
    assert "本期暂无动态" not in text


def test_entity_changes_includes_non_tracked_claim_entity() -> None:
    """主张（claim）中出现但未跟踪的企业也上屏——比亚迪/蔚来等应上屏。"""
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
    # 有动态的 2 家（特来电、比亚迪）都上屏，无动态的国家电网/云快充不占位
    assert any(line.startswith("- 比亚迪：[事实] 比亚迪闪充技术落地") for line in lines)
    assert lines[1].startswith("- 比亚迪：")
    assert len(lines) == 2
    assert "本期暂无动态" not in text


def test_one_liner_skips_excluded_claim() -> None:
    """一句话判断也按 exclude 过滤：跳过跑偏的"手机"类事实，取次高置信度正常事实。"""
    claims = [
        {"claim_id": "c1", "claim_text": "华为手机支持100W有线快充",
         "claim_type": "fact", "confidence": 0.99, "entity_id": "华为",
         "analysis_type": "technology"},
        {"claim_id": "c2", "claim_text": "户用储能装机量同比增长",
         "claim_type": "fact", "confidence": 0.8, "entity_id": "阳光电源",
         "analysis_type": "market"},
    ]
    text = DigestFormatter().render(_bundle(claims=claims, exclude_terms=["手机"]))
    one = text.split("一、本周一句话判断")[1].split("二、最重要的")[0]
    assert "户用储能装机量同比增长" in one
    assert "华为手机" not in one


def test_entity_changes_skips_excluded_claim() -> None:
    """企业节也按 exclude 过滤：跑偏的"手机"类 claim 不上屏。"""
    claims = [
        {"claim_id": "c1", "claim_text": "华为手机在售产品支持100W有线快充",
         "claim_type": "fact", "confidence": 0.9, "entity_id": "华为数字能源",
         "analysis_type": "technology"},
    ]
    companies = [{"name": "华为数字能源"}]
    text = DigestFormatter().render(
        _bundle(claims=claims, companies=companies, exclude_terms=["手机"])
    )
    section = text.split("三、企业竞争变化")[1]
    assert "华为手机" not in section
    assert "- 华为数字能源：" not in section
