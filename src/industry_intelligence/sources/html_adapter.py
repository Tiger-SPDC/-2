"""HTML 页面适配器。

简单标签剥离提取标题与正文，供通用网页采集使用。支持 file:// URI（离线测试用）。
"""

from __future__ import annotations

import html as html_lib
import re

from industry_intelligence.core.document import NormalizedDocument, create_document_id
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.models import ParsedDocument, QueryPlan, RawContent, SourceItem
from industry_intelligence.utils.hashing import content_hash, url_hash
from industry_intelligence.utils.http import fetch_text
from industry_intelligence.utils.url import canonicalize_url

_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_BLOCK_RE = re.compile(
    r"<(script|style|nav|header|footer|head|title)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _extract_html(raw: str) -> tuple[str, str]:
    """从 HTML 文本提取 (标题, 正文纯文本)。"""
    title = ""
    title_match = _TITLE_RE.search(raw)
    if title_match:
        title = html_lib.unescape(_TAG_RE.sub("", title_match.group(1))).strip()
    body = _BLOCK_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", body)
    text = html_lib.unescape(text)
    text = " ".join(text.split())
    return title, text


class HTMLAdapter(SourceAdapter):
    """HTML 网页数据源适配器。"""

    source_id = "html"

    def __init__(
        self,
        source_grade: str = "C",
        timeout: int = 20,
        user_agent: str = "industry-intelligence-agent",
    ) -> None:
        self.source_grade = source_grade
        self._timeout = timeout
        self._user_agent = user_agent

    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        """HTML 适配器不主动发现；条目由上层（搜索计划）提供。"""
        return []

    def fetch(self, item: SourceItem) -> RawContent:
        text = fetch_text(
            item.url, timeout=self._timeout, user_agent=self._user_agent
        )
        return RawContent(
            item_id=item.item_id,
            url=item.url,
            content_type="html",
            raw_text=text or "",
        )

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        title, text = _extract_html(raw.raw_text or "")
        return ParsedDocument(
            url=item.url,
            item_id=item.item_id,
            source_id=item.source_id,
            title=title,
            content_text=text,
            raw_type="html",
            published_at=item.published_at,
        )

    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        canonical = canonicalize_url(parsed.url)
        crc = content_hash(parsed.content_text)
        return NormalizedDocument(
            document_id=create_document_id(canonical, crc),
            canonical_url=canonical,
            source_id=parsed.source_id,
            title=parsed.title,
            content_text=parsed.content_text,
            content_hash=crc,
            url_hash=url_hash(parsed.url),
            source_grade=self.source_grade,
            topic_id=topic_id,
            published_at=parsed.published_at,
            author=parsed.author,
            language=parsed.language,
            summary=parsed.summary,
            raw_type=parsed.raw_type,
        )

    def health_check(self) -> bool:
        return True
