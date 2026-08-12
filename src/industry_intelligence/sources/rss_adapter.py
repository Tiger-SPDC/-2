"""RSS/Atom 适配器。

通过 feedparser 解析 feed；条目内容来自 feed 本身（标题/摘要/发布时间），
不再回访文章页面。支持 file:// URI（离线测试用）。
"""

from __future__ import annotations

from calendar import timegm
from datetime import UTC, datetime
from typing import Any

import feedparser  # type: ignore[import-untyped]

from industry_intelligence.core.document import NormalizedDocument, create_document_id
from industry_intelligence.sources.adapter import SourceAdapter
from industry_intelligence.sources.models import ParsedDocument, QueryPlan, RawContent, SourceItem
from industry_intelligence.utils.hashing import content_hash, url_hash
from industry_intelligence.utils.http import fetch_text
from industry_intelligence.utils.url import canonicalize_url


def _entry_str(entry: Any, key: str) -> str:
    """安全读取 feedparser 条目字段。"""
    value = entry.get(key) if hasattr(entry, "get") else None
    return str(value).strip() if value else ""


def _to_iso(published_parsed: Any) -> str | None:
    """将 feedparser 的 time.struct_time（UTC）转 ISO 8601。"""
    if not published_parsed:
        return None
    dt = datetime.fromtimestamp(timegm(published_parsed), tz=UTC)
    return dt.isoformat(timespec="seconds")


class RSSAdapter(SourceAdapter):
    """RSS/Atom 数据源适配器。"""

    source_id = "rss"

    def __init__(
        self,
        feed_urls: dict[str, str],
        source_grade: str = "C",
        timeout: int = 20,
        user_agent: str = "industry-intelligence-agent",
        max_entries: int = 50,
    ) -> None:
        self._feed_urls = dict(feed_urls)
        self.source_grade = source_grade
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_entries = max_entries

    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        """读取每个 feed，枚举条目为 SourceItem。"""
        items: list[SourceItem] = []
        for feed_id, feed_url in self._feed_urls.items():
            text = fetch_text(
                feed_url, timeout=self._timeout, user_agent=self._user_agent
            )
            if text is None:
                continue
            feed = feedparser.parse(text)
            if not feed.entries:
                continue
            for entry in feed.entries[: self._max_entries]:
                link = _entry_str(entry, "link")
                if not link:
                    continue
                items.append(
                    SourceItem(
                        url=link,
                        item_id=_entry_str(entry, "id") or link,
                        source_id=f"rss:{feed_id}",
                        title=_entry_str(entry, "title"),
                        published_at=_to_iso(entry.get("published_parsed")),
                        extra={
                            "feed_url": feed_url,
                            "summary": _entry_str(entry, "summary"),
                            "author": _entry_str(entry, "author"),
                        },
                    )
                )
        return items

    def fetch(self, item: SourceItem) -> RawContent:
        """RSS 条目的文本来自 feed 条目本身，无需访问文章页面。"""
        summary = str(item.extra.get("summary") or "")
        return RawContent(
            item_id=item.item_id,
            url=item.url,
            content_type="xml",
            raw_text=summary,
            headers={"feed_url": str(item.extra.get("feed_url", ""))},
        )

    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        """将 RSS 条目字段组装为结构化文档。"""
        summary = raw.raw_text or ""
        return ParsedDocument(
            url=item.url,
            item_id=item.item_id,
            source_id=item.source_id,
            title=item.title or "",
            content_text=summary,
            raw_type="rss",
            published_at=item.published_at,
            author=str(item.extra.get("author") or "") or None,
            summary=summary or None,
            extra=dict(item.extra),
        )

    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        """生成标准文档：规范化 URL + 内容/URL 哈希 + document_id。"""
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
            extra=parsed.extra,
        )

    def health_check(self) -> bool:
        return len(self._feed_urls) > 0
