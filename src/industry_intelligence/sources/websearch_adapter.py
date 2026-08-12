"""网页搜索引擎适配器：直接抓取 Bing SERP HTML，无 API Key。

需求背景：真实搜索直接在网页版上进行数据检索（无需注册账号/付费 API Key），
并按行业声明的权威官方域名做 site: 限定检索（官方域名来自 Topic 配置）。

SERP 解析用纯 stdlib ``html.parser.HTMLParser``（无新依赖），
提取 ``<li class="b_algo">`` 结果块内的标题链接与摘要，过滤 Bing/Microsoft 内部链接。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

from industry_intelligence.config.models import WebSearchEngineConfig
from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.html_adapter import HTMLAdapter
from industry_intelligence.sources.models import (
    ParsedDocument,
    QueryPlan,
    RawContent,
    SourceItem,
)
from industry_intelligence.utils.hashing import url_hash
from industry_intelligence.utils.http import fetch_text
from industry_intelligence.utils.url import canonicalize_url

# Bing / Microsoft 内部域名（结果中的站点导航、去重提示等一律排除）
_INTERNAL_HOST_SUFFIXES = (
    "bing.com",
    "microsoft.com",
    "msn.com",
    "go.microsoft.com",
)
# site: 限定操作符（官方站点族查询，如 "充电桩 site:nea.gov.cn"）
_SITE_RE = re.compile(r"\bsite:([A-Za-z0-9.-]+)", re.IGNORECASE)
# 摘要容器的候选 class（Bing 不同地区/版本略有差异）
_SNIPPET_CLASSES = {"b_caption", "b_snippet", "b_lineclamp2", "b_lineclamp3"}


def _is_external_result_href(href: str) -> bool:
    """仅接受 http(s) 的绝对外部结果链接。

    排除：空 href、javascript:/# 等伪链接、Bing/Microsoft 内部站点、
    以 /search、/images 开头的站内路径。
    """
    href = href.strip()
    if not href:
        return False
    try:
        parts = urlparse(href)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if any(
        host == suffix or host.endswith("." + suffix)
        for suffix in _INTERNAL_HOST_SUFFIXES
    ):
        return False
    path = parts.path or ""
    return not (path.startswith("/search") or path.startswith("/images"))


def _resolve_serp_href(href: str, base_url: str) -> str:
    """解析 SERP 中的相对链接为绝对 URL（Bing 偶尔输出相对路径）。"""
    return urljoin(base_url, href)


def _normalize_text(text: str) -> str:
    """空白归一化（合并连续空白、去首尾）。"""
    return " ".join(text.split())


class _SerpParser(HTMLParser):
    """Bing SERP 结果块状态机提取器。

    - ``<li class="b_algo">`` 开启一个结果块，匹配其闭合 ``</li>`` 后输出；
    - 块内取第一个外部 ``<a href>`` 作为标题（含 ``<strong>`` 高亮一并捕获）；
    - ``<div class="b_caption">``（含变体）作为摘要，按 div 嵌套深度匹配闭合。
    """

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url or ""
        self.results: list[dict[str, str]] = []
        self._in_block = False
        self._li_depth = 0
        self._current: dict[str, str] = {}
        self._capture_title = False
        self._title_buf: list[str] = []
        self._capture_snippet = False
        self._snippet_depth = 0
        self._snippet_buf: list[str] = []

    # -- 事件处理 ----------------------------------------------------------
    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        if tag == "li":
            classes = set(attr_dict.get("class", "").split())
            if not self._in_block:
                if "b_algo" in classes:
                    self._in_block = True
                    self._li_depth = 1
                    self._current = {}
            else:
                self._li_depth += 1
        if not self._in_block:
            return
        if tag == "a" and not self._capture_title and not self._current.get("url"):
            href = attr_dict.get("href", "")
            if _is_external_result_href(href):
                self._current["url"] = _resolve_serp_href(href, self._base_url)
                self._title_buf = []
                self._capture_title = True
        elif tag == "div":
            classes = set(attr_dict.get("class", "").split())
            if not self._capture_snippet and classes & _SNIPPET_CLASSES:
                self._capture_snippet = True
                self._snippet_depth = 1
                self._snippet_buf = []
            elif self._capture_snippet:
                self._snippet_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # 自闭合的 <li/>、<div/>、<a/>（Bing 极罕见，但保险起见按开+闭处理）
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_buf.append(data)
        if self._capture_snippet:
            self._snippet_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_block:
            return
        if tag == "a" and self._capture_title:
            self._current["title"] = _normalize_text("".join(self._title_buf))
            self._capture_title = False
        elif tag == "div" and self._capture_snippet:
            self._snippet_depth -= 1
            if self._snippet_depth <= 0:
                self._current["snippet"] = _normalize_text(
                    "".join(self._snippet_buf)
                )
                self._capture_snippet = False
        elif tag == "li":
            self._li_depth -= 1
            if self._li_depth <= 0:
                self._finish_block()

    # -- 内部 --------------------------------------------------------------
    def _finish_block(self) -> None:
        url = self._current.get("url", "")
        title = self._current.get("title", "")
        if url and title:
            self.results.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": self._current.get("snippet", ""),
                }
            )
        self._in_block = False
        self._capture_title = False
        self._capture_snippet = False
        self._current = {}


def _parse_serp_html(
    html: str | None, base_url: str | None = None
) -> list[dict[str, str]]:
    """从 Bing SERP HTML 提取 [{url, title, snippet}]。纯函数，永不抛出。"""
    if not html:
        return []
    parser = _SerpParser(base_url=base_url)
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — 解析容错，异常按零结果处理
        return []
    return parser.results


class WebSearchAdapter(SourceAdapter):
    """网页搜索引擎适配器：直接抓取 Bing SERP HTML，无 API Key。

    - ``discover``：把 QueryPlan 组装为 SERP URL（多 base_url 地理兜底），
      解析结果块为 SourceItem；查询间礼貌 sleep，SERP 为 None/零结果时重试并跳过。
    - ``fetch/parse/normalize``：委托内部 HTMLAdapter（复用其 file:// 支持与正文提取）。
    - 官方站点族（family="official"）在 extra 打上 ``official_domain``，供追溯。
    """

    source_id = "websearch"
    source_grade = "C"

    def __init__(
        self,
        engine: WebSearchEngineConfig,
        *,
        timeout: int = 20,
        delay_seconds: float | None = None,
        user_agent: str | None = None,
        retries: int = 0,
        fetch_text_fn: Callable[..., str | None] = fetch_text,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._engine = engine
        self._enabled = engine.enabled
        self._max_results = engine.max_results
        self._timeout = timeout
        # 引擎优先；未设时由 main.py 传入 system.collection.polite_delay_seconds
        self._delay = (
            delay_seconds if delay_seconds is not None else (engine.delay_seconds or 0.0)
        )
        self._retries = retries
        self._user_agent = user_agent or "industry-intelligence-agent"
        self._fetch_text_fn = fetch_text_fn
        self._sleep_fn = sleep_fn
        self._html = HTMLAdapter(
            source_grade=self.source_grade,
            timeout=timeout,
            user_agent=self._user_agent,
        )

    # -- SourceAdapter 接口 -------------------------------------------------
    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        """把查询计划组装为 Bing SERP 请求并解析出候选条目。"""
        if not queries or not self._enabled:
            return []
        items: list[SourceItem] = []
        seen: set[str] = set()
        budget_remaining = self._max_results
        for idx, plan in enumerate(queries):
            if budget_remaining <= 0:
                break
            # 礼貌限速：查询之间 sleep（首个查询不 sleep）
            if idx > 0 and self._delay > 0:
                self._sleep_fn(self._delay)
            per_query = min(plan.budget, budget_remaining)
            if per_query <= 0:
                continue
            fetched = self._fetch_serp_with_retry(plan.query_string)
            if fetched is None:
                continue
            results, serp_url = fetched
            built = 0
            for result in results:
                if built >= per_query:
                    break
                canonical = canonicalize_url(result["url"])
                if canonical in seen:
                    continue
                seen.add(canonical)
                items.append(self._build_item(result, plan, serp_url))
                built += 1
            budget_remaining -= built
        return items

    def fetch(self, item: SourceItem) -> RawContent:
        return self._html.fetch(item)

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        return self._html.parse(raw, item)

    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        return self._html.normalize(parsed, topic_id)

    def health_check(self) -> bool:
        return self._enabled

    # -- 内部 ---------------------------------------------------------------
    def _fetch_serp_with_retry(
        self, query_string: str
    ) -> tuple[list[dict[str, str]], str] | None:
        """按 base_url 顺序尝试抓取 SERP，首个非空结果即用；失败退避重试。"""
        for base_url in self._engine.base_urls:
            serp_url = self._build_serp_url(base_url, query_string)
            for attempt in range(self._retries + 1):
                text = self._fetch_text_fn(
                    serp_url, timeout=self._timeout, user_agent=self._user_agent
                )
                results = _parse_serp_html(text)
                if results:
                    return results, serp_url
                if attempt < self._retries:
                    self._sleep_fn(self._delay * (attempt + 1))
        return None

    def _build_serp_url(self, base_url: str, query_string: str) -> str:
        params = dict(self._engine.params)
        params["q"] = query_string
        return f"{base_url}?{urlencode(params)}"

    def _build_item(
        self, result: dict[str, str], plan: QueryPlan, serp_url: str
    ) -> SourceItem:
        extra: dict[str, object] = {
            "query_id": plan.query_id,
            "query_string": plan.query_string,
            "family": plan.family,
            "serp_url": serp_url,
            "snippet": result["snippet"],
        }
        if plan.family == "official":
            extra["official_domain"] = self._extract_site_domain(plan.query_string)
        return SourceItem(
            url=result["url"],
            item_id=url_hash(result["url"]),
            source_id=f"{self.source_id}:{self._engine.id}",
            title=result["title"],
            extra=extra,
        )

    @staticmethod
    def _extract_site_domain(query_string: str) -> str:
        match = _SITE_RE.search(query_string)
        return match.group(1).lower() if match else ""
