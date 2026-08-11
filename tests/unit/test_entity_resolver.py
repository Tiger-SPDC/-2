"""实体解析器单元测试。"""

from __future__ import annotations

from industry_intelligence.config.models import CompanyEntity, TopicEntities, TopicProfile
from industry_intelligence.entities import EntityMatch, EntityResolver


def _resolver_for(companies: list[CompanyEntity]) -> EntityResolver:
    topic = TopicProfile(id="t", name="n", version="1", entities=TopicEntities(companies=companies))
    return EntityResolver(topic)


def test_exact_match(sample_topic) -> None:
    matches = EntityResolver(sample_topic).resolve("特来电发布新款充电桩")
    assert [m.canonical_name for m in matches] == ["特来电"]


def test_alias_match(sample_topic) -> None:
    matches = EntityResolver(sample_topic).resolve("特来电新能源宣布合作")
    assert [m.canonical_name for m in matches] == ["特来电"]
    assert matches[0].matched_term == "特来电新能源"


def test_multi_entity(sample_topic) -> None:
    matches = EntityResolver(sample_topic).resolve("特来电与星星充电达成合作")
    assert [m.canonical_name for m in matches] == ["特来电", "星星充电"]


def test_no_match(sample_topic) -> None:
    assert EntityResolver(sample_topic).resolve("完全无关的行业新闻") == []


def test_empty_text(sample_topic) -> None:
    assert EntityResolver(sample_topic).resolve("") == []


def test_duplicate_mentions_dedup(sample_topic) -> None:
    matches = EntityResolver(sample_topic).resolve("特来电与特来电续签合同")
    assert [m.canonical_name for m in matches] == ["特来电"]


def test_casefold_matching() -> None:
    resolver = _resolver_for(
        [CompanyEntity(canonical_name="State Grid", aliases=["StateGrid"])]
    )
    matches = resolver.resolve("partnered with STATEGRID")
    assert [m.canonical_name for m in matches] == ["State Grid"]


def test_match_type_is_entity_match(sample_topic) -> None:
    matches = EntityResolver(sample_topic).resolve("特来电")
    assert isinstance(matches[0], EntityMatch)


def test_resolve_document_fills_matched_entities(sample_topic, make_doc) -> None:
    doc = make_doc(title="特来电获新一轮融资", content_text="")
    EntityResolver(sample_topic).resolve_document(doc)
    assert doc.matched_entities == ["特来电"]


def test_resolve_document_uses_title_and_content(sample_topic, make_doc) -> None:
    doc = make_doc(title="行业快讯", content_text="星星充电公布财报")
    EntityResolver(sample_topic).resolve_document(doc)
    assert doc.matched_entities == ["星星充电"]
