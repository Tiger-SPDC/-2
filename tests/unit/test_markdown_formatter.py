"""MarkdownFormatter 单元测试：15 节结构、空数据节、结论标签（全离线）。"""

from __future__ import annotations

from industry_intelligence.reporting.builder import ReportDataBundle
from industry_intelligence.reporting.formatters.markdown import MarkdownFormatter

_CLAIM = {
    "claim_id": "c1",
    "claim_text": "特来电市占率上升",
    "claim_type": "fact",
    "confidence": 0.9,
    "entity_id": "特来电",
    "analysis_type": "market",
    "evidence": [{"document_id": "d1", "evidence_role": "primary_source"}],
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
            "document_count": 1.0,
            "claim_count": 1.0,
            "evidence_coverage": 1.0,
            "review_count": 1.0,
            "review_reject_count": 0.0,
        },
    )
    kwargs.update(overrides)
    return ReportDataBundle(**kwargs)


def test_render_contains_all_section_headers() -> None:
    md = MarkdownFormatter().render(_bundle())
    for title in (
        "1. 执行摘要", "2. 本周期核心结论", "3. 市场关键数据",
        "4. 竞争格局", "5. 重点企业动态", "6. 产品与技术",
        "7. 价格与渠道", "8. 政策与监管", "9. 投融资/并购/项目",
        "10. 风险信号", "11. 机会判断", "12. 历史趋势比较",
        "13. 下周期重点监测清单", "14. 数据完整性说明",
        "15. 来源与证据附录",
    ):
        assert f"## {title}" in md


def test_empty_bundle_shows_no_data_placeholders() -> None:
    bundle = _bundle(claims=[], events=[], observations=[], documents=[])
    md = MarkdownFormatter().render(bundle)
    assert "本期无高置信度事实结论。" in md
    assert "本期无分析结论。" in md
    assert "本期无企业动态。" in md
    assert "本期无历史趋势数据。" in md


def test_claim_labels_appear() -> None:
    bundle = _bundle(
        claims=[
            {"claim_id": "c1", "claim_text": "事实", "claim_type": "fact",
             "confidence": 0.9, "analysis_type": "market"},
            {"claim_id": "c2", "claim_text": "推断", "claim_type": "inference",
             "confidence": 0.7, "analysis_type": "technology"},
            {"claim_id": "c3", "claim_text": "预测", "claim_type": "forecast",
             "confidence": 0.6, "analysis_type": "risk"},
        ]
    )
    md = MarkdownFormatter().render(bundle)
    assert "[事实]" in md
    assert "[推断]" in md
    assert "[预测]" in md


def test_trend_comparison_renders_values() -> None:
    bundle = _bundle(
        trends={
            "event_velocity": [
                {
                    "indicator_name": "event_velocity",
                    "current_value": 2.0,
                    "previous_value": 1.0,
                    "baseline_avg": 0.5,
                    "delta_pct": 100.0,
                    "entity_id": None,
                }
            ]
        }
    )
    md = MarkdownFormatter().render(bundle)
    assert "### event_velocity" in md
    assert "当前 2.0 / 上周 1.0" in md


def test_data_integrity_lists_quality() -> None:
    md = MarkdownFormatter().render(_bundle())
    assert "证据覆盖率" in md
    assert "已审查结论" in md
