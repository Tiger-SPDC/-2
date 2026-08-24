"""CompanyScorer / CompanyDiscoverer / discover_companies 单元测试（全离线）。

覆盖：LLM 输入 schema、无 provider / LLM 失败降级、关联度打分排序、去固定种子、
企业节不上无动态企业、模板加载。
"""

from __future__ import annotations

from industry_intelligence.intelligence.company_discovery import (
    COMPANY_SCHEMA,
    CompanyDiscoverer,
    CompanyScorer,
    _norm_company,
    _parse_companies,
    discover_companies,
)
from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.reporting.builder import ReportDataBundle


class _FakeProvider(LLMProvider):
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


def _bundle(**overrides) -> ReportDataBundle:
    kwargs: dict[str, object] = dict(
        run_id="r1", topic_id="t1", task_id="tk1", status="success",
        period_start="2026-08-01", period_end="2026-08-24",
        claims=[], events=[], focus_terms=["充电桩", "超充"],
        exclude_terms=["维基百科"], hot_topics=["超充"],
    )
    kwargs.update(overrides)
    return ReportDataBundle(**kwargs)


def test_norm_company_strips_source_and_bracket() -> None:
    """归一化去 ` - 来源` 与括号备注，用于跨源/别名去重。"""
    assert _norm_company("小鹏汽车 - 新浪") == "小鹏汽车"
    assert _norm_company("比亚迪（BYD）") == "比亚迪"
    assert _norm_company(" 特来电新能源 ") == "特来电新能源"


def test_discover_companies_no_provider_uses_claims() -> None:
    """无 provider 时降级只用 claims 内企业，仍能发现非种子，不崩。"""
    bundle = _bundle(claims=[
        {"claim_id": "c1", "claim_text": "小鹏发布超充站", "entity_id": "小鹏汽车",
         "claim_type": "fact", "confidence": 0.9, "analysis_type": "technology"},
    ])
    out = discover_companies(bundle, provider=None)
    names = [str(c["name"]) for c in out]
    assert "小鹏汽车" in names
    assert all(c.get("activity_text") for c in out)


def test_discover_companies_empty_when_no_activity() -> None:
    """无 claim/事件/LLM 上屏企业时不虚假占位（返回空）。"""
    bundle = _bundle(claims=[])
    assert discover_companies(bundle, provider=None) == []


def test_company_scorer_ranks_by_relevance() -> None:
    """关联度排序：出现次数多 + 命中 core 的企业排前。"""
    claims = [
        {"claim_id": "c1", "claim_text": "A充电站投用", "entity_id": "甲",
         "claim_type": "fact", "confidence": 0.9, "analysis_type": "technology"},
        {"claim_id": "c2", "claim_text": "A又建充电网", "entity_id": "甲",
         "claim_type": "fact", "confidence": 0.85, "analysis_type": "market"},
        {"claim_id": "c3", "claim_text": "乙发布储能电池", "entity_id": "乙",
         "claim_type": "fact", "confidence": 0.8, "analysis_type": "technology"},
    ]
    scorer = CompanyScorer(focus_terms=["充电桩", "充电站"], hot_topics=[])
    out = scorer.score_entities(["甲", "乙", "丙"], claims, [])
    names = [str(c["name"]) for c in out]
    # 甲出现 2 次且命中 core，应排最前；丙无动态应被排除（score<=0）
    assert names[0] == "甲"
    assert "丙" not in names


def test_company_scorer_excludes_no_activity_entity() -> None:
    """候选里没有动态的企业（seed 若保留也不上屏）：score<=0 剔除。"""
    claims = [{"claim_id": "c1", "claim_text": "某充电站投用", "entity_id": "甲",
               "claim_type": "fact", "confidence": 0.9, "analysis_type": "technology"}]
    scorer = CompanyScorer(focus_terms=["充电桩"], hot_topics=[])
    out = scorer.score_entities(["甲", "乙"], claims, [])
    names = [str(c["name"]) for c in out]
    assert names == ["甲"]  # 乙无动态被剔除，不占位


def test_discoverer_fetches_companies_from_news() -> None:
    """LLM 正常路径：从新闻提取企业。"""
    provider = _FakeProvider(result={"companies": ["蔚来", "小鹏", "蔚来"]})
    d = CompanyDiscoverer(provider=provider)
    events = [{"event_id": "e1", "title": "蔚来发布超充网络计划"}]
    bodies = {"e1": [{"title": "蔚来超充", "content_text": "蔚来发布第二代超充站。"}]}
    out = d.discover(events, bodies)
    assert out == ["蔚来", "小鹏"]  # 去重


def test_discoverer_no_provider_returns_empty() -> None:
    """无 provider 返回空（不崩），由 discover_companies 降级用既有来源。"""
    d = CompanyDiscoverer(provider=None)
    assert d.discover([], {}) == []


def test_discoverer_llm_error_returns_empty() -> None:
    """LLM 抛 LLMError 降级返回空。"""
    d = CompanyDiscoverer(provider=_FakeProvider(exc=LLMError("boom")))
    events = [{"event_id": "e1", "title": "t"}]
    bodies = {"e1": [{"content_text": "x" * 60}]}
    assert d.discover(events, bodies) == []


def test_parse_companies_tolerant_and_dedup() -> None:
    """容错解析：非 list / 非字符串 / 空串丢弃，去重。"""
    assert _parse_companies({"companies": ["甲", " 甲 ", "", 123, "乙"]}) == ["甲", "乙"]
    assert _parse_companies({"companies": "notalist"}) == []
    assert _parse_companies({}) == []


def test_company_schema_shape() -> None:
    """schema 是 object，companies 是 array of string。"""
    assert COMPANY_SCHEMA["type"] == "object"
    assert COMPANY_SCHEMA["properties"]["companies"]["type"] == "array"
    assert COMPANY_SCHEMA["properties"]["companies"]["items"]["type"] == "string"


def test_discover_companies_from_events_as_well() -> None:
    """events.entity_ids 里的企业（含种子）也进候选，但无 claim 动态文案时才不占位。"""
    bundle = _bundle(
        events=[{"event_id": "e1", "title": "特来电新站开业", "event_date": "2026-08-20",
                 "entity_ids": ["特来电"]}],
    )
    out = discover_companies(bundle, provider=None)
    names = [str(c["name"]) for c in out]
    # 特来电在 event 里出现，有事件标题动态，应上屏
    assert "特来电" in names
