"""文档相关性门控：用主题配置的关键词与企业名判定文档是否与行业相关。

行业内容全部来自 config（TopicProfile），src/ 零行业硬编码。
用途：websearch 等来源抓取的文档若完全不命中主题信号，视为垃圾丢弃，
避免无关内容（如搜索引擎返回的异域旅游页/无关语言文章）污染事件与摘要。
"""

from __future__ import annotations

from industry_intelligence.config.models import TopicProfile
from industry_intelligence.core.document import NormalizedDocument


def build_relevance_terms(topic: TopicProfile) -> list[str]:
    """从主题配置构建相关性信号词（去重、去空、小写）。

    取 core / products / market / technology 四组关键词 + 跟踪企业名与别名。
    events 关键词（如"政策"）过于通用、exclude 为负向词，均不入信号集。
    """
    terms: list[str] = []
    terms.extend(topic.keywords.core)
    terms.extend(topic.keywords.products)
    terms.extend(topic.keywords.market)
    terms.extend(topic.keywords.technology)
    for company in topic.entities.companies:
        terms.append(company.canonical_name)
        terms.extend(company.aliases)
    return sorted({t.strip().lower() for t in terms if t and t.strip()})


def is_relevant(title: str, content: str, terms: list[str]) -> bool:
    """标题或正文命中任一信号词则相关；未配置信号词时不拦截。"""
    if not terms:
        return True
    haystack = f"{title or ''}\n{content or ''}".lower()
    return any(term in haystack for term in terms)


def is_doc_relevant(doc: NormalizedDocument, terms: list[str]) -> bool:
    """文档级相关性判定（采集入口共用）。

    RSS 已由 feed 提供商按查询词预过滤、site: 官方域结果按构造可信，均直接
    放行；其余来源（websearch 等）须命中主题信号词，否则视为垃圾丢弃。
    """
    if doc.source_id.startswith("rss:"):
        return True
    if doc.extra.get("official_domain"):
        return True
    return is_relevant(doc.title, doc.content_text, terms)
