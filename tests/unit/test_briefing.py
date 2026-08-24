"""BriefingGenerator 单元测试：早报提炼的构建、降级回退、容错解析（全离线）。"""

from __future__ import annotations

from industry_intelligence.intelligence.briefing import (
    BRIEFING_SCHEMA,
    BriefingGenerator,
    _parse_briefings,
    _truncate_cn,
    pick_top_events,
)
from industry_intelligence.llm.provider import LLMError, LLMProvider


class _FakeProvider(LLMProvider):
    """确定性 fake：按设定返回结构化结果或抛 LLMError。"""

    def __init__(self, result: dict | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def generate_structured(self, prompt: str, json_schema: dict) -> dict:
        self.calls.append(prompt)
        if self._exc:
            raise self._exc
        assert self._result is not None
        return self._result


def _events() -> list[dict]:
    return [
        {"event_id": "e1", "title": "浙江最大高速重卡充电站在桐庐投运", "event_date": "2026-08-10"},
        {"event_id": "e2", "title": "某地充电站投用", "event_date": "2026-08-09"},
    ]


def _bodies() -> dict[str, list[dict]]:
    return {
        "e1": [{"title": "浙江高速重卡充电站投运", "canonical_url": "https://x/1",
                "content_text": "浙江最大高速重卡充电站在桐庐投运，1小时可充400度电。"}],
        "e2": [],
    }


def test_generate_returns_briefing_by_event_id() -> None:
    """正常路径：按 event_id 返回早报，正文齐全时生成非空 dict。"""
    provider = _FakeProvider(result={
        "items": [
            {"title": "浙江最大高速重卡充电站在桐庐投运",
             "briefing": "浙江最大高速重卡充电站在桐庐投运，一小时可充400度电，缓解卡车补能焦虑。"},
        ]
    })
    gen = BriefingGenerator(provider=provider)
    out = gen.generate(_events(), _bodies())
    assert out == {"e1": "浙江最大高速重卡充电站在桐庐投运，一小时可充400度电，缓解卡车补能焦虑。"}


def test_generate_no_provider_returns_empty() -> None:
    """无 provider 时返回空 dict（绝不虚构），调用方回退原标题。"""
    gen = BriefingGenerator(provider=None)
    assert gen.generate(_events(), _bodies()) == {}


def test_generate_llm_error_returns_empty() -> None:
    """LLM 抛 LLMError 时降级返回空，不崩。"""
    gen = BriefingGenerator(provider=_FakeProvider(exc=LLMError("boom")))
    assert gen.generate(_events(), _bodies()) == {}


def test_generate_no_bodies_returns_empty() -> None:
    """所有事件都无正文时返回空（_build_prompt 返回空串），不调用 LLM。"""
    provider = _FakeProvider(result={"items": []})
    gen = BriefingGenerator(provider=provider)
    assert gen.generate(_events(), {}) == {}
    assert len(provider.calls) == 0


def test_parse_briefings_aligns_by_title_and_truncates() -> None:
    """按 title 对齐回 event_id；非 list/空串/无关标题丢弃；超过 max_len 才截断。"""
    raw = {"items": [
        {"title": "某地充电站投用", "briefing": "某地新充电站今日投用，24小时对外开放。"},
        {"title": "不存在的标题", "briefing": "应被丢弃"},
        {"title": "无早报", "briefing": ""},
    ]}
    # max_len 足够大 → 早报完整返回（验证对齐 + 无关项丢弃）
    out = _parse_briefings(raw, [{"event_id": "e2", "title": "某地充电站投用"}], max_len=100)
    assert out == {"e2": "某地新充电站今日投用，24小时对外开放。"}
    # max_len 过小 → 触发截断且不超过 max_len（用可控素材走 _truncate_cn 单测）
    assert len(_truncate_cn("长" * 100, 30)) <= 30
    assert _truncate_cn("长" * 100, 30).endswith("…")


def test_truncate_cn_prefers_sentence_end() -> None:
    """中文截断：有句末标点就截到句号，不加省略号；无标点才硬截加省略号。"""
    assert _truncate_cn("甲" * 25 + "。" + "乙" * 20, 30) == "甲" * 25 + "。"
    out = _truncate_cn("长" * 100, 30)
    assert out.endswith("…")
    assert len(out) <= 30


def test_briefing_schema_shapes() -> None:
    """schema 是合法的 object，items 项含 title/briefing 且必填。"""
    assert BRIEFING_SCHEMA["type"] == "object"
    items = BRIEFING_SCHEMA["properties"]["items"]
    assert items["type"] == "array"
    assert "title" in items["items"]["properties"]
    assert "briefing" in items["items"]["properties"]


def test_pick_top_events_dedups_same_news_across_sources() -> None:
    """同新闻跨源（标题仅差来源后缀）去重只保留一条，避免早报重复。"""
    from industry_intelligence.reporting.builder import ReportDataBundle

    n1 = "错过服务区下高速充电 导航到被杂草覆盖的充电桩 - 新浪财经"
    n2 = "错过服务区下高速充电 导航到被杂草覆盖的充电桩 - 驱动之家"
    events = [
        {"event_id": "e1", "title": n1, "event_date": "2026-08-23T00:49:16"},
        {"event_id": "e2", "title": n2, "event_date": "2026-08-23T00:21:00"},
        {"event_id": "e3", "title": "某地充电站投用", "event_date": "2026-08-22"},
    ]
    bundle = ReportDataBundle(
        run_id="r1", topic_id="t1", task_id="tk1", status="success",
        period_start="2026-08-01", period_end="2026-08-24",
        events=events, focus_terms=["充电桩", "充电站"],
    )
    picked = pick_top_events(bundle, limit=5)
    ids = [str(e["event_id"]) for e in picked]
    assert "e1" in ids and "e2" not in ids and "e3" in ids


def test_pick_top_events_filters_and_sorts() -> None:
    """pick_top_events 按 focus 过滤、按日期倒序，命中热点排前（与 formatter 一致）。"""
    from industry_intelligence.reporting.builder import ReportDataBundle

    events = [
        {"event_id": "o", "title": "普通汽车新闻", "event_date": "2026-08-11"},
        {"event_id": "h", "title": "液冷超充站落地北京", "event_date": "2026-08-09",
         "summary": "液冷超充 光储充一体化"},
        {"event_id": "c", "title": "某地充电站投用", "event_date": "2026-08-10"},
    ]
    bundle = ReportDataBundle(
        run_id="r1", topic_id="t1", task_id="tk1", status="success",
        period_start="2026-08-01", period_end="2026-08-12",
        events=events,
        focus_terms=["充电桩", "充电站", "超充"],
        exclude_terms=["维基百科"],
        hot_topics=["液冷超充"],
    )
    picked = pick_top_events(bundle, limit=5)
    ids = [str(e["event_id"]) for e in picked]
    assert "h" in ids and "c" in ids
    assert "o" not in ids            # 无 core 词 → 剔除
    # 热点优先：h（命中热点）应排在最前
    assert ids[0] == "h"
    assert "液冷超充站落地北京" in str(picked[0]["title"])
