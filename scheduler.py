#!/usr/bin/env python
"""调度器 CLI（Phase 5，§6.1）：读取 config/schedules.yaml 运行到期任务。

用法：
  python scheduler.py --dry-run                列出今天到期任务，不执行
  python scheduler.py --run-due                运行所有到期任务（GitHub cron 调用）
  python scheduler.py --run-due --force        忽略上次运行记录，强制执行
  python scheduler.py --run-due --retry 1      失败任务自动重试一次
  python scheduler.py --task <task_id>         仅运行指定任务（忽略 cadence）
  python scheduler.py --validate-schedules     校验 schedules.yaml 可解析

环境变量（Secrets，由 GitHub Actions 注入）：
  DEEPSEEK_API_KEY  LLM API Key（透传给 main.py 的 llm.api_key_env）
  SERVERCHAN_KEY    Server酱 SendKey（透传给 main.py 的 notification 段）
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"

#: GitHub 运行时的持久化数据路径（提交回仓库）
DEFAULT_OUTPUT = "data/collection.jsonl"
DEFAULT_DB_PATH = "data/state/industry_intelligence.sqlite"


def _load_timezone_name() -> str | None:
    """读取 system.yaml 的 system.timezone；失败返回 None（退化为本地时区）。"""
    try:
        from industry_intelligence.config.loader import load_system_config

        return load_system_config(CONFIG_DIR / "system.yaml").timezone
    except Exception:  # noqa: BLE001 — 时区读取失败不阻塞调度
        return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="industry-intelligence-scheduler",
        description="Industry Intelligence Agent 通用调度器",
    )
    parser.add_argument("--dry-run", action="store_true", help="列出到期任务，不执行")
    parser.add_argument("--run-due", action="store_true", help="运行所有到期任务")
    parser.add_argument("--force", action="store_true", help="忽略上次运行记录")
    parser.add_argument("--retry", type=int, default=0, help="失败任务自动重试次数")
    parser.add_argument("--task", default=None, help="仅运行指定任务 id（忽略 cadence）")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="JSONL 输出路径")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite 路径")
    parser.add_argument("--validate-schedules", action="store_true", help="仅校验调度配置")

    args = parser.parse_args(argv)

    from industry_intelligence.config.loader import ConfigError
    from industry_intelligence.ops import (
        Scheduler,
        load_schedules,
        today_in_timezone,
    )

    if args.validate_schedules:
        try:
            schedules = load_schedules(CONFIG_DIR)
        except ConfigError as exc:
            print(f"Schedules validation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Schedules validation OK: {len(schedules)} schedule(s)")
        for sid in schedules:
            print(f"  - {sid}")
        return 0

    today = today_in_timezone(_load_timezone_name())
    scheduler = Scheduler(
        config_dir=CONFIG_DIR,
        project_root=PROJECT_ROOT,
        output=args.output,
        db_path=args.db_path,
    )

    if args.dry_run:
        try:
            due = scheduler.list_due(today, force=args.force, only=args.task)
        except ConfigError as exc:
            print(f"Schedules error: {exc}", file=sys.stderr)
            return 1
        print(f"[{today.isoformat()}] {len(due)} task(s) due:")
        for task_id in due:
            print(f"  - {task_id}")
        return 0

    if args.run_due:
        try:
            result = scheduler.run_due(
                today, force=args.force, retry=args.retry, only=args.task
            )
        except ConfigError as exc:
            print(f"Schedules error: {exc}", file=sys.stderr)
            return 1
        print(
            f"[{today.isoformat()}] ran={result.ran} failed={result.failed} "
            f"skipped={result.skipped}"
        )
        for task_id in result.failed:
            print(f"  ! failed: {task_id}")
        return 1 if result.failed else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
