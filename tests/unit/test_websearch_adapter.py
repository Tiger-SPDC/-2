"""WebSearchAdapter 与 Bing SERP 解析器单元测试（全离线）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from industry_intelligence.config.models import WebSearchEngineConfig
from industry_intelligence.sources.models import QueryPlan, SourceItem
from industry_intelligence.sources.websearch_adapter import (
    WebSearchAdapter,
    _is_external_result_href,
    _parse_serp_html,
    _resolve_serp_href,
)
from industry_intelligence.utils.url import canonicalize_url


def _load_bing_fixture(fixtures_dir: Path) -> str:
    return (
        fixtures_dir / "search" / "bing_results.html"
    ).read_text(encoding="utf-8")


def _engine(**overrides) -> WebSearchEngineConfig:
    defaults: dict[str, object] = dict(
        id="bing",
        base_urls=["https://cn.bing.com/search", "https://www.bing.com/search"],
        params={"mkt": "zh-CN"},
        max_results=20,
        delay_seconds=0.0,
        enabled=True,
    )
    defaults.update(overrides)
    return WebSearchEngineConfig(**defaults)


def _plan(query_string: str, **kw) -> QueryPlan:
    return QueryPlan(
        query_id=hashlib.sha256(query_string.encode("utf-8")).hexdigest()[:16],
        query_string=query_string,
        family=kw.pop("family", "general"),
        budget=kw.pop("budget", 10),
    )


def _noop_sleep(_: float) -> None:
    return None


def test_parse_serp_html_extracts_blocks(fixtures_dir: Path) -> None:
    results = _parse_serp_html(_load_bing_fixture(fixtures_dir))
    # 3 个外部结果 + 1 个 bing 内部链接（跳过）+ 1 个非 b_algo 块（跳过）
    assert len(results) == 3
    first = results[0]
    assert first["url"] == "https://www.teld.cn/news/123.html"
    # <strong> 高亮标签应被剥离，标题合并为纯文本
    assert first["title"] == "特来电推出新款液冷超充"
    assert "600kW" in first["snippet"]


def test_parse_serp_html_skips_internal_links(fixtures_dir: Path) -> None:
    results = _parse_serp_html(_load_bing_fixture(fixtures_dir))
    urls = [r["url"] for r in results]
    assert not any("bing.com" in u for u in urls)
    assert not any("microsoft.com" in u for u in urls)


def test_parse_serp_html_no_algo_returns_empty() -> None:
    assert _parse_serp_html("<html><body><p>没有结果</p></body></html>") == []
    assert _parse_serp_html("") == []
    assert _parse_serp_html(None) == []


def test_parse_serp_html_malformed_returns_empty() -> None:
    # 畸形 HTML 不抛错，按零结果处理
    assert _parse_serp_html("<li class=b_algo><h2><a href=>") == []


def test_resolve_serp_href_relative() -> None:
    resolved = _resolve_serp_href(
        "/url?q=https%3A%2F%2Fexample.com%2Fx",
        "https://cn.bing.com/search",
    )
    assert resolved.startswith("https://cn.bing.com/url")


def test_is_external_result_href_matrix() -> None:
    assert _is_external_result_href("https://a.com/x")
    assert _is_external_result_href("https://sub.example.org/path?q=1")
    assert not _is_external_result_href("javascript:void(0)")
    assert not _is_external_result_href("#")
    assert not _is_external_result_href("/search?q=foo")
    assert not _is_external_result_href("https://cn.bing.com/search")
    assert not _is_external_result_href("https://www.msn.com/x")
    assert not _is_external_result_href("https://go.microsoft.com/fwlink")
    assert not _is_external_result_href("")
    assert not _is_external_result_href("ftp://example.com/x")


# ---------------------------------------------------------------------------
# WebSearchAdapter
# ---------------------------------------------------------------------------


def test_discover_builds_items_with_fetch_mock(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    items = adapter.discover([_plan("充电桩 特来电 中国")], context={})
    assert items
    first = items[0]
    assert first.source_id == "websearch:bing"
    assert first.title == "特来电推出新款液冷超充"
    assert first.extra["query_string"] == "充电桩 特来电 中国"
    assert first.extra["family"] == "general"
    assert first.item_id.startswith("url_")
    assert "snippet" in first.extra


def test_discover_stamps_official_domain(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    items = adapter.discover(
        [_plan("充电桩 site:nea.gov.cn", family="official")], context={}
    )
    assert items
    assert all(i.extra["family"] == "official" for i in items)
    assert all(i.extra["official_domain"] == "nea.gov.cn" for i in items)


def test_discover_dedups_urls_across_queries(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    items = adapter.discover([_plan("q1"), _plan("q2")], context={})
    urls = [canonicalize_url(i.url) for i in items]
    assert len(urls) == len(set(urls))
    # fixture 只有 3 个唯一外部结果 → 跨查询去重后仍为 3
    assert len(items) == 3


def test_discover_respects_global_max_results(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(max_results=2),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    items = adapter.discover([_plan("q1"), _plan("q2")], context={})
    assert len(items) == 2


def test_discover_respects_per_query_budget(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    q1 = _plan("q1", budget=1)
    q2 = _plan("q2", budget=10)
    items = adapter.discover([q1, q2], context={})
    assert len(items) == 3
    q1_items = [i for i in items if i.extra["query_id"] == q1.query_id]
    assert len(q1_items) == 1  # 首个查询被 per-query budget=1 截断


def test_discover_graceful_when_fetch_none() -> None:
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: None,
        sleep_fn=_noop_sleep,
    )
    assert adapter.discover([_plan("q1"), _plan("q2")], context={}) == []


def test_discover_politeness_sleep_called_between_queries(
    fixtures_dir: Path,
) -> None:
    html = _load_bing_fixture(fixtures_dir)
    sleeps: list[float] = []
    adapter = WebSearchAdapter(
        _engine(delay_seconds=1.5),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=sleeps.append,
    )
    adapter.discover([_plan("q1"), _plan("q2"), _plan("q3")], context={})
    assert sleeps == [1.5, 1.5]  # 3 个查询之间 2 次限速


def test_discover_base_url_fallback(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    calls: list[str] = []

    def fetch(url: str, **kwargs: object) -> str | None:
        calls.append(url)
        if "cn.bing.com" in url:
            return None  # 地理不可达，尝试下一个 base_url
        return html

    adapter = WebSearchAdapter(
        _engine(), fetch_text_fn=fetch, sleep_fn=_noop_sleep
    )
    items = adapter.discover([_plan("q")], context={})
    assert items
    assert any("www.bing.com" in i.extra["serp_url"] for i in items)
    assert len(calls) >= 2  # cn 失败 → www 兜底


def test_discover_retries_when_serp_empty(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    seq = iter([None, html])
    sleeps: list[float] = []

    def fetch(url: str, **kwargs: object) -> str | None:
        return next(seq)

    adapter = WebSearchAdapter(
        _engine(base_urls=["https://cn.bing.com/search"], delay_seconds=2.0),
        retries=1,
        fetch_text_fn=fetch,
        sleep_fn=sleeps.append,
    )
    items = adapter.discover([_plan("q")], context={})
    assert items
    assert sleeps == [2.0]  # 首次失败后 sleep(delay*1) 再重试


def test_discover_disabled_returns_empty(fixtures_dir: Path) -> None:
    html = _load_bing_fixture(fixtures_dir)
    adapter = WebSearchAdapter(
        _engine(enabled=False),
        fetch_text_fn=lambda *a, **k: html,
        sleep_fn=_noop_sleep,
    )
    assert adapter.discover([_plan("q")], context={}) == []
    assert adapter.health_check() is False


def test_fetch_parse_normalize_delegate_to_html(fixtures_dir: Path) -> None:
    page = fixtures_dir / "html" / "sample_page.html"
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: None,
        sleep_fn=_noop_sleep,
    )
    item = SourceItem(
        url=page.as_uri(), item_id="it1", source_id="websearch:bing", title="T"
    )
    raw = adapter.fetch(item)
    assert raw.content_type == "html"
    parsed = adapter.parse(raw, item)
    assert parsed.source_id == "websearch:bing"
    assert parsed.title or parsed.content_text  # 复用 HTMLAdapter 正文提取
    doc = adapter.normalize(parsed, topic_id="t1")
    assert doc.source_id == "websearch:bing"
    assert doc.raw_type == "html"


def test_extra_survives_to_normalized_document(fixtures_dir: Path) -> None:
    """family / official_domain 标记应贯穿 fetch→parse→normalize→to_dict 全链路。"""
    page = fixtures_dir / "html" / "sample_page.html"
    adapter = WebSearchAdapter(
        _engine(),
        fetch_text_fn=lambda *a, **k: None,
        sleep_fn=_noop_sleep,
    )
    item = SourceItem(
        url=page.as_uri(),
        item_id="it1",
        source_id="websearch:bing",
        title="T",
        extra={
            "family": "official",
            "official_domain": "nea.gov.cn",
            "query_string": "充电桩 site:nea.gov.cn",
            "snippet": "国家能源局通知",
        },
    )
    parsed = adapter.parse(adapter.fetch(item), item)
    assert parsed.extra["official_domain"] == "nea.gov.cn"
    doc = adapter.normalize(parsed, topic_id="t1")
    assert doc.extra["family"] == "official"
    assert doc.extra["official_domain"] == "nea.gov.cn"
    d = doc.to_dict()
    assert d["extra"]["official_domain"] == "nea.gov.cn"
    # JSONL 反序列化（from_dict）后 extra 仍完整，保证追溯能力
    restored = doc.from_dict(d)
    assert restored.extra["official_domain"] == "nea.gov.cn"
    assert restored.extra["query_string"] == "充电桩 site:nea.gov.cn"
