"""相关性门控工具单元测试（全离线）。"""

from __future__ import annotations

from industry_intelligence.config.models import (
    CompanyEntity,
    TopicEntities,
    TopicKeywords,
    TopicProfile,
    TopicScope,
)
from industry_intelligence.utils.relevance import build_relevance_terms, is_relevant


def _topic(**overrides) -> TopicProfile:
    kwargs: dict[str, object] = dict(
        id="t1",
        name="测试",
        version="1.0",
        scope=TopicScope(regions=["中国"], default_window_days=7),
        entities=TopicEntities(
            companies=[CompanyEntity(canonical_name="特来电", aliases=["特来电新能源"])]
        ),
        keywords=TopicKeywords(
            core=["充电桩"],
            products=["液冷超充"],
            market=["运营商"],
            technology=["车网互动", "V2G"],
        ),
        metrics=[],
    )
    kwargs.update(overrides)
    return TopicProfile(**kwargs)


def test_build_terms_contains_keywords_and_companies() -> None:
    terms = build_relevance_terms(_topic())
    assert "充电桩" in terms
    assert "液冷超充" in terms
    assert "车网互动" in terms
    assert "特来电" in terms
    assert "特来电新能源" in terms


def test_build_terms_dedups_and_lowercases() -> None:
    terms = build_relevance_terms(
        _topic(keywords=TopicKeywords(core=["充电桩", "充电桩"], technology=["V2G"]))
    )
    assert terms.count("充电桩") == 1
    assert "v2g" in terms
    assert terms == sorted(set(terms))


def test_build_terms_skips_generic_event_words() -> None:
    # events 关键词（政策/招标）不入信号集，避免误放行
    terms = build_relevance_terms(_topic(keywords=TopicKeywords(core=["充电桩"], events=["政策"])))
    assert "政策" not in terms


def test_is_relevant_matches_title() -> None:
    assert is_relevant("特来电推出液冷超充新品", "", ["充电桩", "特来电"])


def test_is_relevant_matches_content() -> None:
    assert is_relevant("无关标题", "充电基础设施发展报告发布", ["充电基础设施"])


def test_is_relevant_case_insensitive() -> None:
    assert is_relevant("V2G 车网互动落地", "", ["v2g"]) is True
    assert is_relevant("plain english page", "", ["充电桩", "v2g"]) is False


def test_is_relevant_rejects_unrelated() -> None:
    assert is_relevant(
        "Brisbane Story Bridge Climb", "Australia tourism", ["充电桩", "特来电"]
    ) is False


def test_is_relevant_no_terms_passes_everything() -> None:
    assert is_relevant("anything", "content", []) is True
