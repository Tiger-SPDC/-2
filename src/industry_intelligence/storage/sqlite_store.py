"""可重建 SQLite 查询层（Phase 2）。

JSONL 为事实源，SQLite 可 DROP 后由 Pipeline 重建。WAL 模式 + 外键约束，
全部写入使用参数化查询。列表字段（matched_entities 等）存 JSON TEXT。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from industry_intelligence.core.document import NormalizedDocument
from industry_intelligence.intelligence.models import Event
from industry_intelligence.metrics.models import Observation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    documents_collected INTEGER NOT NULL DEFAULT 0,
    documents_deduped INTEGER NOT NULL DEFAULT 0,
    events_created INTEGER NOT NULL DEFAULT 0,
    observations_extracted INTEGER NOT NULL DEFAULT 0,
    errors TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    source_grade TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    published_at TEXT,
    author TEXT,
    language TEXT,
    summary TEXT,
    matched_entities TEXT NOT NULL DEFAULT '[]',
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    raw_type TEXT NOT NULL,
    parser_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    topic_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    UNIQUE(entity_id, alias)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type_id TEXT NOT NULL,
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL NOT NULL,
    topic_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_documents (
    event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, document_id)
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    metric_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    period_start TEXT,
    period_end TEXT,
    region TEXT,
    confidence REAL NOT NULL,
    evidence_text TEXT NOT NULL DEFAULT ''
);
"""


class SQLiteStore:
    """SQLite 写入与查询。传入 ``:memory:`` 可离线测试。"""

    def __init__(self, db_path: str | Path = "data/state/industry_intelligence.sqlite") -> None:
        self._path = str(db_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.rebuild()

    def rebuild(self) -> None:
        """幂等建表。"""
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def drop_all(self) -> None:
        """删除全部业务表（JSONL 为事实源，SQLite 可 DROP 后重建）。"""
        tables = (
            "event_documents",
            "observations",
            "events",
            "entity_aliases",
            "entities",
            "documents",
            "runs",
        )
        with self._conn:
            for table in tables:
                self._conn.execute(f"DROP TABLE IF EXISTS {table}")

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ 写入

    def insert_document(self, doc: NormalizedDocument) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    document_id, canonical_url, source_id, title, content_text,
                    content_hash, url_hash, source_grade, topic_id, fetched_at,
                    published_at, author, language, summary, matched_entities,
                    matched_keywords, raw_type, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.document_id,
                    doc.canonical_url,
                    doc.source_id,
                    doc.title,
                    doc.content_text,
                    doc.content_hash,
                    doc.url_hash,
                    doc.source_grade,
                    doc.topic_id,
                    doc.fetched_at,
                    doc.published_at,
                    doc.author,
                    doc.language,
                    doc.summary,
                    json.dumps(doc.matched_entities, ensure_ascii=False),
                    json.dumps(doc.matched_keywords, ensure_ascii=False),
                    doc.raw_type,
                    doc.parser_version,
                ),
            )

    def insert_entity(
        self,
        entity_id: str,
        canonical_name: str,
        aliases: list[str],
        topic_id: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO entities (entity_id, canonical_name, topic_id)"
                " VALUES (?, ?, ?)",
                (entity_id, canonical_name, topic_id),
            )
            for alias in aliases:
                if not alias:
                    continue
                self._conn.execute(
                    "INSERT OR IGNORE INTO entity_aliases (entity_id, alias) VALUES (?, ?)",
                    (entity_id, alias),
                )

    def insert_event(self, event: Event) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    event_id, event_type_id, title, event_date, summary, confidence, topic_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type_id,
                    event.title,
                    event.event_date,
                    event.summary,
                    event.confidence,
                    event.topic_id,
                ),
            )
            for document_id in event.document_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO event_documents (event_id, document_id)"
                    " VALUES (?, ?)",
                    (event.event_id, document_id),
                )

    def insert_observation(self, obs: Observation) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO observations (
                    observation_id, document_id, metric_id, entity_id, value, unit,
                    period_start, period_end, region, confidence, evidence_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.observation_id,
                    obs.document_id,
                    obs.metric_id,
                    obs.entity_id,
                    obs.value,
                    obs.unit,
                    obs.period_start,
                    obs.period_end,
                    obs.region,
                    obs.confidence,
                    obs.evidence_text,
                ),
            )

    def insert_run(
        self, run_id: str, topic_id: str, task_id: str, started_at: str
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (run_id, topic_id, task_id, started_at, status)"
                " VALUES (?, ?, ?, ?, 'running')",
                (run_id, topic_id, task_id, started_at),
            )

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        documents_collected: int = 0,
        documents_deduped: int = 0,
        events_created: int = 0,
        observations_extracted: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                UPDATE runs SET finished_at = ?, status = ?, documents_collected = ?,
                documents_deduped = ?, events_created = ?, observations_extracted = ?,
                errors = ? WHERE run_id = ?
                """,
                (
                    finished_at,
                    status,
                    documents_collected,
                    documents_deduped,
                    events_created,
                    observations_extracted,
                    json.dumps(errors or [], ensure_ascii=False),
                    run_id,
                ),
            )

    # ------------------------------------------------------------------ 查询

    def query_events(
        self, topic_id: str, event_type_id: str | None = None
    ) -> list[sqlite3.Row]:
        """按主题查询事件，可按事件类型过滤。"""
        sql = "SELECT * FROM events WHERE topic_id = ?"
        params: list[object] = [topic_id]
        if event_type_id:
            sql += " AND event_type_id = ?"
            params.append(event_type_id)
        sql += " ORDER BY event_date"
        return self._conn.execute(sql, params).fetchall()

    def query_observations(
        self, topic_id: str, metric_id: str | None = None
    ) -> list[sqlite3.Row]:
        """按主题查询观测，可按指标过滤，按数值降序。"""
        sql = (
            "SELECT o.* FROM observations o"
            " JOIN documents d ON d.document_id = o.document_id"
            " WHERE d.topic_id = ?"
        )
        params: list[object] = [topic_id]
        if metric_id:
            sql += " AND o.metric_id = ?"
            params.append(metric_id)
        sql += " ORDER BY o.value DESC"
        return self._conn.execute(sql, params).fetchall()
