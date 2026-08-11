"""持久化层：JSONL/CSV 事实数据与可重建 SQLite 查询层（Phase 2+）。"""

from industry_intelligence.storage.jsonl_store import JSONLStore

__all__ = ["JSONLStore"]
