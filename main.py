"""Industry Intelligence Agent — 命令行入口。

用法：
  python main.py --version                         显示版本
  python main.py --validate                        校验全部配置
  python main.py --topic <id> --task <id> [--output <jsonl>]          运行采集链路
  python main.py --topic <id> --task <id> --phase2 [--rebuild-db]    完整分析链路
  python main.py --topic <id> --task <id> --phase2 --phase3          Phase 2+3（竞争情报分析）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from industry_intelligence.version import __version__

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "collection.jsonl"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口，返回进程退出码。"""
    parser = argparse.ArgumentParser(
        prog="industry-intelligence-agent",
        description="Industry Intelligence Agent — 通用产业竞争情报自动化",
    )
    parser.add_argument("--version", action="store_true", help="显示版本号")
    parser.add_argument("--validate", action="store_true", help="校验全部配置")
    parser.add_argument("--topic", help="Topic id")
    parser.add_argument("--task", help="Task id")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 JSONL 路径")
    parser.add_argument("--phase2", action="store_true", help="运行 Phase 2 完整分析链路")
    parser.add_argument(
        "--phase3", action="store_true",
        help="在 Phase 2 基础上运行 Phase 3 竞争情报分析（需同时指定 --phase2）",
    )
    parser.add_argument(
        "--phase4", action="store_true",
        help="在 Phase 2+3 基础上执行 Phase 4 审查与报告（需同时指定 --phase2 --phase3）",
    )
    default_report_dir = str(PROJECT_ROOT / "output" / "reports")
    parser.add_argument("--report-dir", default=default_report_dir, help="报告输出目录")
    parser.add_argument("--rebuild-db", action="store_true", help="重建 SQLite（删除全部业务表）")
    default_db = str(PROJECT_ROOT / "data" / "state" / "industry_intelligence.sqlite")
    parser.add_argument("--db-path", default=default_db, help="SQLite 路径")
    # Phase 5：manual_run 工作流覆盖参数（patch 已解析的 Task 配置，不落库）
    parser.add_argument("--days", type=int, default=None, help="覆盖时间窗口（天）")
    parser.add_argument("--regions", default=None, help="覆盖采集地区（逗号分隔）")
    parser.add_argument("--companies", default=None, help="覆盖关注企业（逗号分隔）")
    parser.add_argument("--focus", default=None, help="覆盖核心词（逗号分隔）")
    parser.add_argument(
        "--depth", choices=["quick", "standard", "deep"], default=None,
        help="覆盖采集深度",
    )
    parser.add_argument(
        "--notify", choices=["true", "false"], default=None,
        help="覆盖是否推送微信摘要",
    )

    args = parser.parse_args(argv)

    if args.version:
        print(f"industry-intelligence-agent {__version__}")
        return 0
    if args.validate:
        return _cmd_validate()
    if args.topic and args.task:
        if args.phase2:
            if args.phase4 and not args.phase3:
                print("--phase4 需要同时指定 --phase3；本次跳过审查与报告阶段。")
            return _cmd_run_phase2(
                args.topic, args.task, args.output, args.db_path, args.rebuild_db,
                phase3=args.phase3, phase4=args.phase4 and args.phase3,
                report_dir=args.report_dir,
                days=args.days, regions=args.regions, companies=args.companies,
                focus=args.focus, depth=args.depth, notify=args.notify,
            )
        if args.phase3:
            print("--phase3 需要同时指定 --phase2；本次仅运行采集链路。")
        if args.phase4:
            print("--phase4 需要同时指定 --phase2 --phase3；本次仅运行采集链路。")
        return _cmd_run(
            args.topic, args.task, args.output,
            days=args.days, regions=args.regions, companies=args.companies,
            focus=args.focus, depth=args.depth, notify=args.notify,
        )

    parser.print_help()
    return 0


def _cmd_validate() -> int:
    """校验 config/ 下全部 Topic 与 Task 配置。"""
    from industry_intelligence.config.loader import (
        ConfigError,
        load_event_types,
        load_system_config,
        load_task,
        load_topic,
        resolve_task,
    )

    errors: list[str] = []
    try:
        sys_cfg = load_system_config(CONFIG_DIR / "system.yaml")
        _validate_analysis_dimensions(sys_cfg, errors)
    except ConfigError as exc:
        errors.append(str(exc))
    try:
        load_event_types(CONFIG_DIR)
    except ConfigError as exc:
        errors.append(str(exc))

    topics: dict[str, object] = {}
    for path in sorted((CONFIG_DIR / "topics").glob("*.yaml")):
        topic_id = path.stem
        if topic_id.startswith("_"):
            continue
        try:
            topics[topic_id] = load_topic(topic_id, config_dir=CONFIG_DIR)
        except ConfigError as exc:
            errors.append(str(exc))

    task_count = 0
    for path in sorted((CONFIG_DIR / "tasks").glob("*.yaml")):
        task_id = path.stem
        if task_id.startswith("_"):
            continue
        task_count += 1
        try:
            task = load_task(task_id, config_dir=CONFIG_DIR)
            if task.topic_id not in topics:
                errors.append(
                    f"Task '{task_id}' references unknown topic '{task.topic_id}'"
                )
                continue
            resolve_task(task, topics[task.topic_id])  # type: ignore[arg-type]
        except ConfigError as exc:
            errors.append(str(exc))

    if errors:
        print(f"Validation failed: {len(errors)} error(s)")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"Validation OK: {len(topics)} topic(s), {task_count} task(s)")
    return 0


def _validate_analysis_dimensions(sys_cfg: Any, errors: list[str]) -> None:
    """校验 analysis.enabled_dimensions 均为已知分析维度。"""
    from industry_intelligence.analysis.models import ANALYSIS_TYPES

    for dim in sys_cfg.analysis.enabled_dimensions:
        if dim not in ANALYSIS_TYPES:
            errors.append(
                f"analysis.enabled_dimensions contains unknown dimension {dim!r}"
            )


def _apply_task_overrides(
    task: Any,
    *,
    days: int | None = None,
    regions: str | None = None,
    companies: str | None = None,
    focus: str | None = None,
    depth: str | None = None,
    notify: str | None = None,
) -> None:
    """用 CLI 覆盖参数 patch 已解析的 TaskConfig（Phase 5 manual_run 工作流）。

    覆盖参数均来自命令行，非配置硬编码；未提供的项保持原值。
    """
    from industry_intelligence.config.models import TaskOverrides

    if days is not None:
        task.window.days = days
    if regions or companies or focus:
        overrides = task.overrides if task.overrides is not None else TaskOverrides()
        if regions:
            overrides.regions = [r.strip() for r in regions.split(",") if r.strip()]
        if companies:
            overrides.companies = [c.strip() for c in companies.split(",") if c.strip()]
        if focus:
            overrides.focus = [f.strip() for f in focus.split(",") if f.strip()]
        task.overrides = overrides
    if depth is not None:
        task.output.depth = depth
    if notify is not None:
        task.output.notify = notify == "true"


def _cmd_run(
    topic_id: str, task_id: str, output: str,
    *,
    days: int | None = None, regions: str | None = None,
    companies: str | None = None, focus: str | None = None,
    depth: str | None = None, notify: str | None = None,
) -> int:
    """执行最小可用采集链路。"""
    from industry_intelligence.collectors import SearchPlanner
    from industry_intelligence.config.loader import (
        ConfigError,
        load_system_config,
        load_task,
        load_topic,
        resolve_task,
    )
    from industry_intelligence.normalization import Deduplicator
    from industry_intelligence.storage import JSONLStore
    from industry_intelligence.utils.relevance import (
        build_relevance_terms,
        is_doc_relevant,
    )

    try:
        sys_cfg = load_system_config(CONFIG_DIR / "system.yaml")
        topic = load_topic(topic_id, config_dir=CONFIG_DIR)
        task = resolve_task(load_task(task_id, config_dir=CONFIG_DIR), topic)
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    _apply_task_overrides(
        task, days=days, regions=regions, companies=companies,
        focus=focus, depth=depth, notify=notify,
    )

    plans = SearchPlanner().generate_plans(topic, task)
    print(f"Planner: {len(plans)} query plan(s) for topic '{topic.id}'")

    adapter = _build_adapter(sys_cfg)
    if not adapter.health_check():
        print(
            "No sources configured in config/sources/search.yaml; nothing to collect."
        )
        return 0

    store = JSONLStore(output)
    dedup = Deduplicator()
    terms = build_relevance_terms(topic)

    collected = 0
    duplicates = 0
    filtered = 0
    for item in adapter.discover(plans, context={}):
        try:
            raw = adapter.fetch(item)
            parsed = adapter.parse(raw, item)
            doc = adapter.normalize(parsed, topic_id=topic.id)
        except Exception as exc:  # noqa: BLE001 — 单条失败不中断整体
            print(f"  ! skipped {item.url}: {exc}")
            continue
        # 相关性门控：与 Pipeline._collect 同规则（RSS/官方站点放行，其余须命中信号）
        if not is_doc_relevant(doc, terms):
            filtered += 1
            continue
        if dedup.register(doc):
            store.append(doc)
            collected += 1
        else:
            duplicates += 1

    print(
        f"Collected {collected} new document(s), "
        f"{duplicates} duplicate(s), {filtered} filtered (irrelevant)."
    )
    print(f"Output: {store.path}")
    return 0


def _cmd_run_phase2(
    topic_id: str, task_id: str, output: str, db_path: str, rebuild_db: bool,
    phase3: bool = False, phase4: bool = False,
    report_dir: str | None = None,
    days: int | None = None, regions: str | None = None,
    companies: str | None = None, focus: str | None = None,
    depth: str | None = None, notify: str | None = None,
) -> int:
    """执行 Phase 2 完整链路（采集 + 实体/事件/观测 + SQLite 持久化）。

    phase3=True 时追加 Phase 3 竞争情报分析（4 分析师 + 内部指数 + 历史比较）。
    phase4=True 时追加 Phase 4 审查（Review Agent）与报告（Markdown/Excel/摘要）。
    """
    from industry_intelligence.collectors import SearchPlanner
    from industry_intelligence.config.loader import (
        ConfigError,
        load_event_types,
        load_system_config,
        load_task,
        load_topic,
        resolve_task,
    )
    from industry_intelligence.controller import Pipeline
    from industry_intelligence.entities import EntityResolver
    from industry_intelligence.intelligence import EventClassifier, EventClusterer
    from industry_intelligence.llm import DeepSeekProvider, LLMError, load_prompt
    from industry_intelligence.metrics import ObservationExtractor
    from industry_intelligence.storage import JSONLStore, SQLiteStore

    try:
        sys_cfg = load_system_config(CONFIG_DIR / "system.yaml")
        topic = load_topic(topic_id, config_dir=CONFIG_DIR)
        task = resolve_task(load_task(task_id, config_dir=CONFIG_DIR), topic)
        event_types = load_event_types(CONFIG_DIR)
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return 1

    _apply_task_overrides(
        task, days=days, regions=regions, companies=companies,
        focus=focus, depth=depth, notify=notify,
    )

    try:
        provider = DeepSeekProvider(sys_cfg.llm)
    except LLMError as exc:
        print(f"LLM config error: {exc}")
        return 1

    adapter = _build_adapter(sys_cfg)
    if not adapter.health_check():
        print("No sources configured in config/sources/search.yaml; nothing to collect.")
        return 0

    jsonl_store = JSONLStore(output)
    sqlite_store = SQLiteStore(db_path)
    if rebuild_db:
        sqlite_store.drop_all()
        sqlite_store.rebuild()
        print(f"SQLite rebuilt: {db_path}")

    analysis_engine = None
    if phase3:
        from industry_intelligence.analysis.engine import AnalysisEngine
        from industry_intelligence.analysis.models import (
            ANALYSIS_COMPETITOR,
            ANALYSIS_MARKET,
            ANALYSIS_RISK,
            ANALYSIS_TECHNOLOGY,
        )

        analysis_engine = AnalysisEngine(
            provider=provider,
            sqlite_store=sqlite_store,
            topic=topic,
            task=task,
            prompts={
                ANALYSIS_COMPETITOR: load_prompt("competitor_analysis", CONFIG_DIR),
                ANALYSIS_MARKET: load_prompt("market_analysis", CONFIG_DIR),
                ANALYSIS_TECHNOLOGY: load_prompt("technology_analysis", CONFIG_DIR),
                ANALYSIS_RISK: load_prompt("risk_analysis", CONFIG_DIR),
            },
            analysis_config=sys_cfg.analysis,
        )

    review_agent = None
    report_engine = None
    notification_adapter = None
    if phase4:
        from industry_intelligence.analysis.review import ReviewAgent
        from industry_intelligence.notification import ServerChanAdapter
        from industry_intelligence.reporting import ReportEngine

        review_agent = ReviewAgent(
            provider=provider,
            sqlite_store=sqlite_store,
            prompt_template=load_prompt("review", CONFIG_DIR),
            topic=topic,
            task=task,
            review_config=sys_cfg.review,
        )
        report_engine = ReportEngine(
            sqlite_store=sqlite_store,
            topic=topic,
            task=task,
            report_config=sys_cfg.report,
            output_dir=report_dir or (PROJECT_ROOT / "output" / "reports"),
        )
        notification_adapter = ServerChanAdapter(
            sendkey=os.environ.get(sys_cfg.notification.serverchan_key_env),
            retry=sys_cfg.notification.retry,
            timeout_seconds=sys_cfg.notification.timeout_seconds,
        )

    resolver = EntityResolver(topic)
    classifier = EventClassifier(
        provider=provider,
        event_types=event_types,
        keywords=topic.keywords.events,
        prompt_template=load_prompt("classification", CONFIG_DIR),
    )
    extractor = ObservationExtractor(
        provider=provider,
        prompt_template=load_prompt("extraction", CONFIG_DIR),
    )
    pipeline = Pipeline(
        topic=topic,
        task=task,
        system_config=sys_cfg,
        adapter=adapter,
        jsonl_store=jsonl_store,
        sqlite_store=sqlite_store,
        entity_resolver=resolver,
        event_classifier=classifier,
        observation_extractor=extractor,
        planner=SearchPlanner(),
        event_clusterer=EventClusterer(),
        analysis_engine=analysis_engine,
        review_agent=review_agent,
        report_engine=report_engine,
        notification_adapter=notification_adapter,
    )

    result = pipeline.run()
    summary = (
        f"Run {result.run_id} [{result.status}]: "
        f"{result.documents_collected} doc(s), "
        f"{result.documents_deduped} dup(s), "
        f"{result.events_created} event(s), "
        f"{result.observations_extracted} observation(s)"
    )
    if phase3:
        summary += (
            f", {result.analysis_claims} claim(s), "
            f"evidence coverage {result.evidence_coverage:.0%}"
        )
    if phase4:
        summary += (
            f", review {result.review_passed} pass/"
            f"{result.review_rejected} reject/{result.review_downgraded} downgrade"
        )
        if result.report_paths:
            summary += (
                ", reports: "
                + ", ".join(result.report_paths.get(k, "") for k in ("markdown", "excel"))
            )
        if result.notification_sent:
            summary += ", notified"
    print(summary)
    for msg in result.errors:
        print(f"  ! {msg}")
    print(f"Output: {jsonl_store.path}")
    return 0 if result.status != "failed" else 1


def _load_rss_feeds() -> dict[str, str]:
    """从 config/sources/search.yaml 读取 rss_feeds（行业数据在配置，不在代码）。"""
    sources_path = CONFIG_DIR / "sources" / "search.yaml"
    if not sources_path.is_file():
        return {}
    try:
        data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    feeds = data.get("rss_feeds", {})
    if not isinstance(feeds, dict):
        return {}
    return {str(k): str(v) for k, v in feeds.items() if v}


def _load_websearch_config() -> Any:
    """从 config/sources/search.yaml 读取 websearch 段（缺失→默认禁用）。"""
    from industry_intelligence.config.loader import load_websearch_config

    return load_websearch_config(CONFIG_DIR)


def _build_adapter(sys_cfg: Any) -> Any:
    """构建 [RSS, WebSearch] 组合适配器；websearch 禁用时回退 RSS-only。

    行业数据全部来自 config（rss_feeds / websearch 引擎 / topic 官方域名），
    此处只做装配，不含任何行业硬编码。
    """
    from industry_intelligence.sources import (
        CompositeAdapter,
        RSSAdapter,
        WebSearchAdapter,
    )

    adapters: list[Any] = []
    feeds = _load_rss_feeds()
    if feeds:
        adapters.append(
            RSSAdapter(
                feeds,
                timeout=sys_cfg.collection.request_timeout_seconds,
                user_agent=sys_cfg.collection.user_agent,
            )
        )
    web = _load_websearch_config()
    if web.enabled:
        for engine in web.engines:
            if not engine.enabled:
                continue
            adapters.append(
                WebSearchAdapter(
                    engine,
                    timeout=sys_cfg.collection.request_timeout_seconds,
                    delay_seconds=(
                        engine.delay_seconds
                        or sys_cfg.collection.polite_delay_seconds
                    ),
                    user_agent=engine.user_agent or sys_cfg.collection.user_agent,
                    retries=sys_cfg.collection.retries,
                )
            )
    return CompositeAdapter(adapters)


if __name__ == "__main__":
    sys.exit(main())
