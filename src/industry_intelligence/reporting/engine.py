"""报告引擎（Phase 4）：按 ReportConfig 开关渲染 Markdown / Excel / 微信摘要。

ReportEngine 依赖 ReportDataBuilder 构建 bundle，再调用对应 formatter。
单个格式失败不中断其它格式（记录到 errors）。报告写入 output/reports/{run_id}/。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from industry_intelligence.config.models import ReportConfig, TaskConfig, TopicProfile
from industry_intelligence.reporting.builder import ReportDataBuilder
from industry_intelligence.reporting.formatters.digest import DigestFormatter
from industry_intelligence.reporting.formatters.excel import ExcelFormatter
from industry_intelligence.reporting.formatters.markdown import MarkdownFormatter
from industry_intelligence.storage import SQLiteStore

FORMAT_MARKDOWN = "markdown"
FORMAT_EXCEL = "excel"
FORMAT_DIGEST = "digest"


@dataclass
class ReportEngineResult:
    """一次报告生成的结果汇总。"""

    run_id: str
    paths: dict[str, str] = field(default_factory=dict)
    digest_text: str = ""
    errors: list[str] = field(default_factory=list)


class ReportEngine:
    """编排数据构建与 3 种格式化器，把报告写入磁盘。"""

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        topic: TopicProfile,
        task: TaskConfig,
        report_config: ReportConfig | None = None,
        output_dir: str | Path = "output/reports",
    ) -> None:
        self._store = sqlite_store
        self._topic = topic
        self._task = task
        self._config = report_config or ReportConfig()
        self._output_dir = Path(output_dir)

    def run(
        self,
        run_id: str,
        *,
        analysis_claims: int = 0,
        evidence_coverage: float = 0.0,
        indices: Sequence[object] | None = None,
        trends: Mapping[str, Sequence[object]] | None = None,
        errors: Sequence[str] | None = None,
    ) -> ReportEngineResult:
        result = ReportEngineResult(run_id=run_id)
        try:
            bundle = ReportDataBuilder(
                self._store, self._topic, self._task
            ).build(
                run_id,
                analysis_claims=analysis_claims,
                evidence_coverage=evidence_coverage,
                indices=indices,
                trends=trends,
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001 — 数据构建失败不中断 pipeline
            result.errors.append(f"report build: {exc}")
            return result

        run_dir = self._output_dir / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result.errors.append(f"report dir {run_dir}: {exc}")
            return result

        if self._config.markdown:
            try:
                md = MarkdownFormatter().render(bundle)
                path = run_dir / "report.md"
                path.write_text(md, encoding="utf-8")
                result.paths[FORMAT_MARKDOWN] = str(path)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"report markdown: {exc}")

        if self._config.excel:
            try:
                data = ExcelFormatter().render(bundle)
                path = run_dir / "report.xlsx"
                path.write_bytes(data)
                result.paths[FORMAT_EXCEL] = str(path)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"report excel: {exc}")

        if self._config.wechat_digest:
            try:
                md_path = result.paths.get(FORMAT_MARKDOWN, "")
                digest = DigestFormatter().render(bundle, report_path=md_path)
                result.digest_text = digest
                path = run_dir / "digest.txt"
                path.write_text(digest, encoding="utf-8")
                result.paths[FORMAT_DIGEST] = str(path)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"report digest: {exc}")

        result.errors.extend(bundle.errors)
        return result
