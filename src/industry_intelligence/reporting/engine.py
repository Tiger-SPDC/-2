"""报告引擎（Phase 4）：按 ReportConfig 开关渲染 Markdown / Excel / 微信摘要。

ReportEngine 依赖 ReportDataBuilder 构建 bundle，再调用对应 formatter。
单个格式失败不中断其它格式（记录到 errors）。报告写入 output/reports/{run_id}/。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from industry_intelligence.config.models import ReportConfig, TaskConfig, TopicProfile
from industry_intelligence.intelligence.briefing import (
    BriefingGenerator,
    fetch_event_bodies,
    pick_top_events,
)
from industry_intelligence.intelligence.company_discovery import discover_companies
from industry_intelligence.llm.provider import LLMProvider
from industry_intelligence.reporting.builder import ReportDataBuilder, ReportDataBundle
from industry_intelligence.reporting.formatters.digest import DigestFormatter
from industry_intelligence.reporting.formatters.excel import ExcelFormatter
from industry_intelligence.reporting.formatters.markdown import MarkdownFormatter
from industry_intelligence.storage import SQLiteStore

FORMAT_MARKDOWN = "markdown"
FORMAT_EXCEL = "excel"
FORMAT_DIGEST = "digest"


def _repo_relative(path: str) -> str:
    """把报告绝对路径转成相对仓库根的展示路径（正斜杠）。

    GitHub runner 的绝对路径（/home/runner/work/...）既点不开、又浪费推送预算；
    相对路径 output/reports/<run_id>/report.md 既可读又省字。转不了时回退原值。
    """
    if not path:
        return ""
    p = Path(path)
    try:
        rel = p.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return p.as_posix()
    return rel.as_posix()


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
        provider: LLMProvider | None = None,
        briefing_enabled: bool = False,
        briefing_prompt: str = "",
        company_discovery_enabled: bool = False,
        company_prompt: str = "",
    ) -> None:
        self._store = sqlite_store
        self._topic = topic
        self._task = task
        self._config = report_config or ReportConfig()
        self._output_dir = Path(output_dir)
        self._provider = provider
        self._briefing_enabled = briefing_enabled
        self._briefing_prompt = briefing_prompt
        self._company_discovery_enabled = company_discovery_enabled
        self._company_prompt = company_prompt

    def run(
        self,
        run_id: str,
        *,
        analysis_claims: int = 0,
        evidence_coverage: float = 0.0,
        indices: Sequence[object] | None = None,
        trends: Mapping[str, Sequence[object]] | None = None,
        errors: Sequence[str] | None = None,
        hot_topics: Sequence[str] | None = None,
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
                hot_topics=hot_topics,
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
                self._apply_briefings(bundle)
            except Exception as exc:  # noqa: BLE001 — 提炼失败不中断推送，回退标题
                result.errors.append(f"event briefing: {exc}")
                bundle.briefings = {}
            try:
                self._apply_company_discovery(bundle)
            except Exception as exc:  # noqa: BLE001 — 企业发现失败降级，回退空
                result.errors.append(f"company discovery: {exc}")
                bundle.discovered_companies = []
            try:
                md_path = result.paths.get(FORMAT_MARKDOWN, "")
                digest = DigestFormatter().render(
                    bundle, report_path=_repo_relative(md_path)
                )
                result.digest_text = digest
                path = run_dir / "digest.txt"
                path.write_text(digest, encoding="utf-8")
                result.paths[FORMAT_DIGEST] = str(path)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"report digest: {exc}")

        result.errors.extend(bundle.errors)
        return result

    def _apply_briefings(self, bundle: ReportDataBundle) -> None:
        """对 top 事件回访正文 + LLM 提炼，写入 bundle.briefings。

        enabled 且 provider 存在时才执行；无正文 / LLM 失败由生成器降级返回空，
        formatter 回退用原标题。结果写入 bundle.briefings（event_id -> 早报句）。
        """
        if not self._briefing_enabled or self._provider is None:
            return
        top = pick_top_events(bundle)
        if not top:
            return
        bodies = fetch_event_bodies(bundle)
        gen = BriefingGenerator(
            provider=self._provider, prompt_template=self._briefing_prompt
        )
        bundle.briefings = gen.generate(top, bodies)

    def _apply_company_discovery(self, bundle: ReportDataBundle) -> None:
        """完全动态发现企业 + 关联度排序，写入 bundle.discovered_companies。

        enabled 且 provider 存在时才做 LLM 提取；无 provider / LLM 失败降级只用
        claims/events 内企业（仍能发现非种子）。结果供 digest 企业节上屏。
        """
        if not self._company_discovery_enabled:
            return
        # provider 可为 None：此时 LLM 提取降级为空，仍用 claims/events 内既有企业做
        # 确定性关联度排序，企业节不空。
        bundle.discovered_companies = discover_companies(
            bundle,
            provider=self._provider,
            prompt_template=self._company_prompt,
        )
