"""Source Adapter 抽象接口。

所有新数据源必须实现本接口并注册到 sources 包，不得在业务逻辑中写网站特例。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.sources.models import ParsedDocument, QueryPlan, RawContent, SourceItem


class SourceAdapter(ABC):
    """数据源适配器基类。"""

    source_id: str
    source_grade: str

    @abstractmethod
    def discover(
        self, queries: list[QueryPlan], context: dict[str, object]
    ) -> list[SourceItem]:
        """根据查询计划发现候选采集条目。"""

    @abstractmethod
    def fetch(self, item: SourceItem) -> RawContent:
        """抓取原始内容。"""

    @abstractmethod
    def parse(self, raw: RawContent, item: SourceItem) -> ParsedDocument:
        """解析原始内容为结构化文档。"""

    @abstractmethod
    def normalize(self, parsed: ParsedDocument, topic_id: str) -> NormalizedDocument:
        """转换为标准化文档（生成哈希与 document_id）。"""

    @abstractmethod
    def health_check(self) -> bool:
        """检查适配器可用性。"""
