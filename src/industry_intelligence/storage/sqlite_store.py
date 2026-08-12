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
from industry_intelligence.utils.relevance import is_relevant

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
    analysis_claims INTEGER NOT NULL DEFAULT 0,
    evidence_coverage REAL NOT NULL DEFAULT 0,
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
    topic_id TEXT NOT NULL,
    entity_ids TEXT NOT NULL DEFAULT '[]'
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

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL
        CHECK (claim_type IN ('fact', 'inference', 'forecast', 'unknown')),
    confidence REAL NOT NULL,
    entity_id TEXT,
    analysis_type TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    observation_id TEXT REFERENCES observations(observation_id) ON DELETE SET NULL,
    evidence_role TEXT NOT NULL DEFAULT 'primary_source'
        CHECK (evidence_role IN ('primary_source', 'cross_validation', 'context')),
    CHECK (document_id IS NOT NULL OR observation_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS claim_reviews (
    review_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    verdict TEXT NOT NULL
        CHECK (verdict IN ('pass', 'reject', 'downgrade')),
    downgrade_to TEXT CHECK (
        downgrade_to IS NULL
        OR downgrade_to IN ('fact', 'inference', 'forecast', 'unknown')
    ),
    issues TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    reviewed_at TEXT NOT NULL
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
        """幂等建表；对旧 runs 表做无损列迁移。"""
        with self._conn:
            self._conn.executescript(_SCHEMA)
            self._ensure_runs_columns()

    def _ensure_runs_columns(self) -> None:
        """老库 runs 表缺少 Phase 3 字段时补列（SQLite 无法在 IF NOT EXISTS 中加列）。

        SQLite 可 DROP 后重建（JSONL 为事实源），此处仅为旧库兼容。
        """
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        for name, ddl in (
            ("analysis_claims", "INTEGER NOT NULL DEFAULT 0"),
            ("evidence_coverage", "REAL NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                self._conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")

    def drop_all(self) -> None:
        """删除全部业务表（JSONL 为事实源，SQLite 可 DROP 后重建）。"""
        tables = (
            "claim_reviews",
            "claim_evidence",
            "claims",
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
        # 用 upsert（ON CONFLICT DO UPDATE）而非 INSERT OR REPLACE：
        # REPLACE 是 DELETE+INSERT，会触发 claim_evidence.document_id 的
        # ON DELETE SET NULL，若该证据行 observation_id 也为空则违反 CHECK
        # （document_id IS NOT NULL OR observation_id IS NOT NULL）。
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO documents (
                    document_id, canonical_url, source_id, title, content_text,
                    content_hash, url_hash, source_grade, topic_id, fetched_at,
                    published_at, author, language, summary, matched_entities,
                    matched_keywords, raw_type, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    canonical_url = excluded.canonical_url,
                    source_id = excluded.source_id,
                    title = excluded.title,
                    content_text = excluded.content_text,
                    content_hash = excluded.content_hash,
                    url_hash = excluded.url_hash,
                    source_grade = excluded.source_grade,
                    topic_id = excluded.topic_id,
                    fetched_at = excluded.fetched_at,
                    published_at = excluded.published_at,
                    author = excluded.author,
                    language = excluded.language,
                    summary = excluded.summary,
                    matched_entities = excluded.matched_entities,
                    matched_keywords = excluded.matched_keywords,
                    raw_type = excluded.raw_type,
                    parser_version = excluded.parser_version
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
                    event_id, event_type_id, title, event_date, summary, confidence,
                    topic_id, entity_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type_id,
                    event.title,
                    event.event_date,
                    event.summary,
                    event.confidence,
                    event.topic_id,
                    json.dumps(event.entity_ids, ensure_ascii=False),
                ),
            )
            for document_id in event.document_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO event_documents (event_id, document_id)"
                    " VALUES (?, ?)",
                    (event.event_id, document_id),
                )

    def insert_observation(self, obs: Observation) -> None:
        # upsert（ON CONFLICT DO UPDATE）而非 INSERT OR REPLACE：
        # REPLACE 会触发 claim_evidence.observation_id 的 ON DELETE SET NULL，
        # 与 document_id 同为 NULL 时违反 CHECK（与 insert_document 同理）。
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO observations (
                    observation_id, document_id, metric_id, entity_id, value, unit,
                    period_start, period_end, region, confidence, evidence_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    document_id = excluded.document_id,
                    metric_id = excluded.metric_id,
                    entity_id = excluded.entity_id,
                    value = excluded.value,
                    unit = excluded.unit,
                    period_start = excluded.period_start,
                    period_end = excluded.period_end,
                    region = excluded.region,
                    confidence = excluded.confidence,
                    evidence_text = excluded.evidence_text
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

    def insert_claim(
        self,
        claim_id: str,
        claim_text: str,
        claim_type: str,
        confidence: float,
        analysis_type: str,
        topic_id: str,
        run_id: str,
        entity_id: str | None = None,
    ) -> None:
        """写入一条分析 Claim（参数化，主键冲突时覆盖）。"""
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO claims (
                    claim_id, claim_text, claim_type, confidence, entity_id,
                    analysis_type, topic_id, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    claim_text,
                    claim_type,
                    confidence,
                    entity_id,
                    analysis_type,
                    topic_id,
                    run_id,
                ),
            )

    def insert_claim_evidence(
        self,
        claim_id: str,
        document_id: str | None = None,
        observation_id: str | None = None,
        evidence_role: str = "primary_source",
    ) -> None:
        """为 Claim 挂接一条证据；至少需要 document_id 或 observation_id 之一。"""
        if document_id is None and observation_id is None:
            raise ValueError("claim_evidence requires document_id or observation_id")
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO claim_evidence (
                    claim_id, document_id, observation_id, evidence_role
                ) VALUES (?, ?, ?, ?)
                """,
                (claim_id, document_id, observation_id, evidence_role),
            )

    def insert_claim_review(
        self,
        review_id: str,
        claim_id: str,
        verdict: str,
        run_id: str,
        downgrade_to: str | None = None,
        issues: list[str] | None = None,
        reason: str = "",
        reviewed_at: str | None = None,
    ) -> None:
        """写入一条 Claim 审查结论（verdict ∈ pass/reject/downgrade）。"""
        if verdict not in ("pass", "reject", "downgrade"):
            raise ValueError(f"invalid review verdict: {verdict!r}")
        if verdict == "downgrade" and downgrade_to is None:
            raise ValueError("downgrade verdict requires downgrade_to")
        stamp = reviewed_at or datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO claim_reviews (
                    review_id, claim_id, verdict, downgrade_to, issues,
                    reason, run_id, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    claim_id,
                    verdict,
                    downgrade_to,
                    json.dumps(issues or [], ensure_ascii=False),
                    reason,
                    run_id,
                    stamp,
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
        analysis_claims: int = 0,
        evidence_coverage: float = 0.0,
        errors: list[str] | None = None,
    ) -> None:
        finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                UPDATE runs SET finished_at = ?, status = ?, documents_collected = ?,
                documents_deduped = ?, events_created = ?, observations_extracted = ?,
                analysis_claims = ?, evidence_coverage = ?, errors = ? WHERE run_id = ?
                """,
                (
                    finished_at,
                    status,
                    documents_collected,
                    documents_deduped,
                    events_created,
                    observations_extracted,
                    analysis_claims,
                    evidence_coverage,
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

    # -------------------------------------------------------- Phase 3 历史查询

    def query_events_in_range(
        self,
        topic_id: str,
        start_date: str,
        end_date: str,
        event_type_id: str | None = None,
    ) -> list[sqlite3.Row]:
        """按时间窗口查询事件（闭区间，ISO 时间字符串比较）。"""
        sql = (
            "SELECT * FROM events"
            " WHERE topic_id = ? AND event_date >= ? AND event_date <= ?"
        )
        params: list[object] = [topic_id, start_date, end_date]
        if event_type_id:
            sql += " AND event_type_id = ?"
            params.append(event_type_id)
        sql += " ORDER BY event_date"
        return self._conn.execute(sql, params).fetchall()

    def query_observations_in_range(
        self,
        topic_id: str,
        metric_id: str | None = None,
        entity_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        """按时间窗口查询观测。

        观测归属窗口取其 period_end；period 缺失时回退到文档 fetched_at。
        """
        sql = (
            "SELECT o.* FROM observations o"
            " JOIN documents d ON d.document_id = o.document_id"
            " WHERE d.topic_id = ?"
        )
        params: list[object] = [topic_id]
        if metric_id:
            sql += " AND o.metric_id = ?"
            params.append(metric_id)
        if entity_id:
            sql += " AND o.entity_id = ?"
            params.append(entity_id)
        if start_date:
            sql += " AND COALESCE(o.period_end, d.fetched_at) >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND COALESCE(o.period_end, d.fetched_at) <= ?"
            params.append(end_date)
        sql += " ORDER BY o.value DESC"
        return self._conn.execute(sql, params).fetchall()

    def query_documents_by_entity(
        self,
        topic_id: str,
        entity_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        """按实体查询文档（documents.matched_entities JSON 数组包含该实体）。"""
        sql = (
            "SELECT * FROM documents d"
            " WHERE d.topic_id = ?"
            " AND EXISTS ("
            "   SELECT 1 FROM json_each(d.matched_entities) WHERE json_each.value = ?"
            " )"
        )
        params: list[object] = [topic_id, entity_id]
        if start_date:
            sql += " AND d.fetched_at >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND d.fetched_at <= ?"
            params.append(end_date)
        sql += " ORDER BY d.fetched_at"
        return self._conn.execute(sql, params).fetchall()

    def query_documents_in_range(
        self,
        topic_id: str,
        start_date: str,
        end_date: str,
    ) -> list[sqlite3.Row]:
        """按时间窗口查询文档（fetched_at 落在闭区间内）。"""
        return self._conn.execute(
            "SELECT * FROM documents WHERE topic_id = ?"
            " AND fetched_at >= ? AND fetched_at <= ?"
            " ORDER BY fetched_at",
            (topic_id, start_date, end_date),
        ).fetchall()

    def purge_irrelevant_documents(self, terms: list[str]) -> int:
        """删除来源为 websearch 且不命中相关性词条的文档及其级联数据。

        仅针对非 RSS/官方来源的垃圾文档（如搜索引擎返回的无关异域页面），
        返回删除的文档数。级联顺序先摘证据/事件链接（避免 ON DELETE SET NULL
        触发 claim_evidence 的 CHECK），再删孤立事件、观察与文档本身。
        """
        if not terms:
            return 0
        candidates = self._conn.execute(
            "SELECT document_id, title, content_text FROM documents"
            " WHERE source_id LIKE 'websearch:%'"
        ).fetchall()
        doc_ids = [
            str(r["document_id"])
            for r in candidates
            if not is_relevant(str(r["title"] or ""), str(r["content_text"] or ""), terms)
        ]
        if not doc_ids:
            return 0
        placeholders = ",".join("?" * len(doc_ids))
        # 收集这些文档的观察，一并摘除证据链接
        obs_ids = [
            str(r["observation_id"])
            for r in self._conn.execute(
                f"SELECT observation_id FROM observations"
                f" WHERE document_id IN ({placeholders})",
                doc_ids,
            ).fetchall()
        ]
        if obs_ids:
            self._conn.execute(
                f"DELETE FROM claim_evidence WHERE observation_id IN"
                f" ({','.join('?' * len(obs_ids))})",
                obs_ids,
            )
        self._conn.execute(
            f"DELETE FROM claim_evidence WHERE document_id IN ({placeholders})",
            doc_ids,
        )
        self._conn.execute(
            f"DELETE FROM event_documents WHERE document_id IN ({placeholders})",
            doc_ids,
        )
        # 删除不再关联任何文档的孤立事件
        self._conn.execute(
            "DELETE FROM events WHERE event_id NOT IN"
            " (SELECT DISTINCT event_id FROM event_documents)"
        )
        self._conn.execute(
            f"DELETE FROM observations WHERE document_id IN ({placeholders})",
            doc_ids,
        )
        self._conn.execute(
            f"DELETE FROM documents WHERE document_id IN ({placeholders})",
            doc_ids,
        )
        self._conn.commit()
        return len(doc_ids)

    def query_events_by_entity(
        self,
        topic_id: str,
        entity_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[sqlite3.Row]:
        """按实体查询事件（events.entity_ids JSON 数组包含该实体）。"""
        sql = (
            "SELECT e.* FROM events e"
            " WHERE e.topic_id = ?"
            " AND EXISTS ("
            "   SELECT 1 FROM json_each(e.entity_ids) WHERE json_each.value = ?"
            " )"
        )
        params: list[object] = [topic_id, entity_id]
        if start_date:
            sql += " AND e.event_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND e.event_date <= ?"
            params.append(end_date)
        sql += " ORDER BY e.event_date"
        return self._conn.execute(sql, params).fetchall()

    def query_prior_runs(self, topic_id: str, limit: int = 10) -> list[sqlite3.Row]:
        """查询主题下最近的成功运行记录（按开始时间倒序）。"""
        return self._conn.execute(
            "SELECT * FROM runs WHERE topic_id = ? AND status = 'success'"
            " ORDER BY started_at DESC LIMIT ?",
            (topic_id, limit),
        ).fetchall()

    def count_events_by_type(
        self,
        topic_id: str,
        entity_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, int]:
        """按事件类型计数（可选实体 / 时间窗口过滤），返回 {event_type_id: count}。"""
        sql = "SELECT event_type_id, COUNT(*) AS cnt FROM events e WHERE e.topic_id = ?"
        params: list[object] = [topic_id]
        if entity_id:
            sql += (
                " AND EXISTS ("
                "   SELECT 1 FROM json_each(e.entity_ids) WHERE json_each.value = ?"
                " )"
            )
            params.append(entity_id)
        if start_date:
            sql += " AND e.event_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND e.event_date <= ?"
            params.append(end_date)
        sql += " GROUP BY event_type_id"
        rows = self._conn.execute(sql, params).fetchall()
        return {row["event_type_id"]: int(row["cnt"]) for row in rows}

    def query_claims(self, run_id: str) -> list[sqlite3.Row]:
        """查询某次运行的分析 Claim。"""
        return self._conn.execute(
            "SELECT * FROM claims WHERE run_id = ? ORDER BY claim_id", (run_id,)
        ).fetchall()

    def query_claim_evidence(self, claim_id: str) -> list[sqlite3.Row]:
        """查询某条 Claim 的证据。"""
        return self._conn.execute(
            "SELECT * FROM claim_evidence WHERE claim_id = ?", (claim_id,)
        ).fetchall()

    def query_claim_reviews(self, run_id: str) -> list[sqlite3.Row]:
        """查询某次运行的全部 Claim 审查结论。"""
        return self._conn.execute(
            "SELECT * FROM claim_reviews WHERE run_id = ? ORDER BY claim_id",
            (run_id,),
        ).fetchall()

    def query_claims_with_evidence(self, run_id: str) -> list[sqlite3.Row]:
        """查询某次运行的 Claim，并 LEFT JOIN 证据（同一条 Claim 多证据时多行）。

        返回列：claims.* + document_id, observation_id, evidence_role。
        供 Review Agent 与报告引擎直接组装可追溯的 Claim+Evidence 视图。
        """
        return self._conn.execute(
            """
            SELECT c.*, ce.document_id, ce.observation_id, ce.evidence_role
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.run_id = ?
            ORDER BY c.claim_id
            """,
            (run_id,),
        ).fetchall()
