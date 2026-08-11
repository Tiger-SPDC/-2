"""通用调度器（Phase 5，§6.1）：按 config/schedules.yaml 判断到期任务并执行。

GitHub Actions 每日固定时刻（如北京 08:17）调用 scheduler.py，本模块读取
schedules.yaml，判断今天哪些任务到期，依次通过 ``main.py`` 执行完整链路
（Phase 2 + 3 + 4）。上次运行记录写入 data/state/scheduler_state.json，
避免同一天重复触发。

纯判定逻辑（``is_due`` / ``load_schedules`` / ``SchedulerState``）完全确定性，
不访问网络，可离线单测。
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from industry_intelligence.config.loader import ConfigError

logger = logging.getLogger(__name__)

#: 支持的调度频率
SCHEDULE_CADENCES = ("daily", "weekly", "monthly")

#: 相对项目根的调度状态文件（提交回仓库，供幂等判断）
DEFAULT_STATE_PATH = Path("data/state/scheduler_state.json")


@dataclass
class TaskSchedule:
    """一条任务调度规则（config/schedules.yaml -> schedules.<task_id>）。"""

    task_id: str
    cadence: str = "daily"
    weekday: int = 0           # Python date.weekday(): 0=周一 … 6=周日（仅 weekly）
    day: int = 1               # 每月几号运行，1-31（仅 monthly）
    local_time: str = "08:00"  # "HH:MM" 本地时间
    depth: str = "standard"    # quick | standard | deep
    notify: bool = True        # 是否推送微信摘要

    def __post_init__(self) -> None:
        if self.cadence not in SCHEDULE_CADENCES:
            raise ConfigError(
                f"schedules.{self.task_id}.cadence 无效: {self.cadence!r}"
                f"（允许 {SCHEDULE_CADENCES}）"
            )
        if not 0 <= self.weekday <= 6:
            raise ConfigError(f"schedules.{self.task_id}.weekday 需在 0-6（0=周一）")
        if not 1 <= self.day <= 31:
            raise ConfigError(f"schedules.{self.task_id}.day 需在 1-31")
        self.local_time = _normalize_hhmm(self.local_time, self.task_id)


def _normalize_hhmm(value: str, task_id: str) -> str:
    """校验并规范化 "HH:MM"（允许 "8:17"，归一为 "08:17"）。"""
    try:
        hour_s, minute_s = value.split(":")
        hour, minute = int(hour_s), int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        raise ConfigError(
            f"schedules.{task_id}.local_time 需为 \"HH:MM\"，例如 \"08:17\""
        ) from None
    return f"{hour:02d}:{minute:02d}"


def load_schedules(config_dir: Path | str) -> dict[str, TaskSchedule]:
    """读取 config/schedules.yaml，返回 {task_id: TaskSchedule}。

    文件缺失返回空映射（调度器不报错，退化为无任务）。
    """
    path = Path(config_dir) / "schedules.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: YAML 解析失败: {exc}") from exc
    raw = data.get("schedules", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: 顶层 `schedules:` 需为映射")
    result: dict[str, TaskSchedule] = {}
    for task_id, item in raw.items():
        if not isinstance(item, dict):
            raise ConfigError(f"{path}: schedules.{task_id} 需为映射")
        result[str(task_id)] = TaskSchedule(
            task_id=str(task_id),
            cadence=str(item.get("cadence", "daily")),
            weekday=int(item.get("weekday", 0)),
            day=int(item.get("day", 1)),
            local_time=str(item.get("local_time", "08:00")),
            depth=str(item.get("depth", "standard")),
            notify=bool(item.get("notify", True)),
        )
    return result


def is_due(schedule: TaskSchedule, today: date) -> bool:
    """判断任务在今天（today）是否到期。纯确定性，时区由调用方决定。"""
    if schedule.cadence == "daily":
        return True
    if schedule.cadence == "weekly":
        return today.weekday() == schedule.weekday
    if schedule.cadence == "monthly":
        return today.day == schedule.day
    return False


@dataclass
class SchedulerState:
    """调度幂等状态：记录每个 task 最近一次实际运行的日期。"""

    last_run: dict[str, str] = field(default_factory=dict)  # task_id -> "YYYY-MM-DD"

    @classmethod
    def load(cls, path: Path | str) -> SchedulerState:
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        last = data.get("last_run", {}) if isinstance(data, dict) else {}
        return cls(last_run={str(k): str(v) for k, v in last.items()})

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"last_run": self.last_run}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def already_ran(self, task_id: str, today: date) -> bool:
        return self.last_run.get(task_id) == today.isoformat()

    def mark_ran(self, task_id: str, today: date) -> None:
        self.last_run[task_id] = today.isoformat()


@dataclass
class SchedulerResult:
    """一次调度会话的结果汇总。"""

    due: list[str] = field(default_factory=list)      # 今天到期任务 id
    skipped: list[str] = field(default_factory=list)  # 今天已运行而跳过
    ran: list[str] = field(default_factory=list)      # 实际执行成功
    failed: list[str] = field(default_factory=list)   # 执行失败（含重试后）
    errors: list[str] = field(default_factory=list)


class Scheduler:
    """读取 schedules.yaml，对到期任务依次调用 main.py 执行完整链路。"""

    def __init__(
        self,
        *,
        config_dir: Path | str,
        project_root: Path | str,
        state_path: Path | str | None = None,
        output: str | None = None,
        db_path: str | None = None,
        python: str | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self._config_dir = Path(config_dir)
        self._root = Path(project_root)
        self._state_path = (
            Path(state_path) if state_path else Path(self._root / DEFAULT_STATE_PATH)
        )
        self._output = output
        self._db_path = db_path
        self._python = python or sys.executable
        self._timeout = timeout_seconds

    def list_due(
        self,
        today: date | None = None,
        *,
        force: bool = False,
        only: str | None = None,
    ) -> list[str]:
        """返回今天到期的任务 id（按 schedules.yaml 顺序）。

        force=True 忽略上次运行记录；only 指定时忽略 cadence 但保留幂等检查。
        """
        today = today or date.today()
        state = SchedulerState.load(self._state_path)
        result: list[str] = []
        for schedule in load_schedules(self._config_dir).values():
            if only is not None and schedule.task_id != only:
                continue
            due = True if only is not None else is_due(schedule, today)
            if not due:
                continue
            if force or not state.already_ran(schedule.task_id, today):
                result.append(schedule.task_id)
        return result

    def run_due(
        self,
        today: date | None = None,
        *,
        force: bool = False,
        retry: int = 0,
        only: str | None = None,
    ) -> SchedulerResult:
        """运行到期（或 only 指定）的任务；成功后写入幂等状态。"""
        today = today or date.today()
        state = SchedulerState.load(self._state_path)
        result = SchedulerResult()

        for schedule in load_schedules(self._config_dir).values():
            if only is not None and schedule.task_id != only:
                continue
            due = True if only is not None else is_due(schedule, today)
            if not due:
                continue
            if state.already_ran(schedule.task_id, today) and not force:
                result.skipped.append(schedule.task_id)
                continue

            result.due.append(schedule.task_id)
            ok = self._run_task(schedule)
            if not ok and retry > 0:
                logger.warning(
                    "task %s 首次执行失败，自动重试", schedule.task_id
                )
                ok = self._run_task(schedule)
            if ok:
                state.mark_ran(schedule.task_id, today)
                result.ran.append(schedule.task_id)
            else:
                result.failed.append(schedule.task_id)

        state.save(self._state_path)
        return result

    def _run_task(self, schedule: TaskSchedule) -> bool:
        """调用 main.py 执行单个任务的完整链路；返回是否成功。"""
        from industry_intelligence.config.loader import load_task

        try:
            task = load_task(schedule.task_id, config_dir=self._config_dir)
        except ConfigError as exc:
            logger.error("任务 %s 配置错误: %s", schedule.task_id, exc)
            return False
        if not task.enabled:
            logger.info("任务 %s 已禁用，跳过", schedule.task_id)
            return True  # 禁用视为无需运行，不算失败

        cmd = [
            self._python,
            str(self._root / "main.py"),
            "--topic",
            task.topic_id,
            "--task",
            task.id,
            "--phase2",
            "--phase3",
            "--phase4",
        ]
        if self._output:
            cmd += ["--output", self._output]
        if self._db_path:
            cmd += ["--db-path", self._db_path]
        if schedule.depth:
            cmd += ["--depth", schedule.depth]
        cmd += ["--notify", "true" if schedule.notify else "false"]
        logger.info("运行任务 %s: %s", schedule.task_id, " ".join(cmd))
        try:
            proc = subprocess.run(cmd, cwd=self._root, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            logger.error("任务 %s 超时（%ss）", schedule.task_id, self._timeout)
            return False
        except OSError as exc:
            logger.error("任务 %s 无法启动进程: %s", schedule.task_id, exc)
            return False
        return proc.returncode == 0


def today_in_timezone(timezone_name: str | None) -> date:
    """返回指定 IANA 时区的今天日期；无法解析时退化为系统本地时区。

    仅 CLI 使用；纯逻辑测试直接传入 date，不依赖系统时区数据库。
    """
    if timezone_name:
        try:
            from zoneinfo import ZoneInfo

            return datetime.now(ZoneInfo(timezone_name)).date()
        except Exception:  # noqa: BLE001 — 时区库缺失时降级
            logger.warning("时区 %s 无法解析，使用系统本地时区", timezone_name)
    return datetime.now().astimezone().date()
