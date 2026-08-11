"""报告引擎（Phase 4）：Markdown / Excel / 微信摘要。"""

from industry_intelligence.reporting.builder import ReportDataBuilder, ReportDataBundle
from industry_intelligence.reporting.engine import (
    FORMAT_DIGEST,
    FORMAT_EXCEL,
    FORMAT_MARKDOWN,
    ReportEngine,
    ReportEngineResult,
)
from industry_intelligence.reporting.formatters.digest import DigestFormatter
from industry_intelligence.reporting.formatters.excel import ExcelFormatter
from industry_intelligence.reporting.formatters.markdown import MarkdownFormatter

__all__ = [
    "DigestFormatter",
    "ExcelFormatter",
    "FORMAT_DIGEST",
    "FORMAT_EXCEL",
    "FORMAT_MARKDOWN",
    "MarkdownFormatter",
    "ReportDataBuilder",
    "ReportDataBundle",
    "ReportEngine",
    "ReportEngineResult",
]
