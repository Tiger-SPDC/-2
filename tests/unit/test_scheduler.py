"""通用调度器单元测试（Phase 5，全离线）。

纯逻辑（load_schedules / is_due / SchedulerState / 幂等）确定性测试；
Scheduler.run_due 通过 mock subprocess 与 load_task 验证命令构造与状态写入。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from industry_intelligence.config.loader import ConfigError
from industry_intelligence.config.models import TaskConfig
from industry_intelligence.ops import (
    Scheduler,
    SchedulerState,
    TaskSchedule,
    is_due,
    load_schedules,
)

WEEKLY_YAML = """
schedules:
  weekly_job:
    task_id: weekly_job
    cadence: weekly
    weekday: 1
    local_time: "08:17"
    depth: standard
    notify: true
"""


def _write_schedules(tmp_path: Path, content: str = WEEKLY_YAML) -> Path:
    (tmp_path / "schedules.yaml").write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- load_schedules


def test_load_schedules_missing_file_returns_empty(tmp_path) -> None:
    assert load_schedules(tmp_path) == {}


def test_load_schedules_parses_entry(tmp_path) -> None:
    cfg = _write_schedules(tmp_path)
    schedules = load_schedules(cfg)
    assert list(schedules) == ["weekly_job"]
    s = schedules["weekly_job"]
    assert s.task_id == "weekly_job"
    assert s.cadence == "weekly"
    assert s.weekday == 1
    assert s.local_time == "08:17"
    assert s.notify is True


def test_load_schedules_normalizes_local_time(tmp_path) -> None:
    cfg = _write_schedules(tmp_path, "schedules:\n  j:\n    task_id: j\n    local_time: '8:17'\n")
    assert load_schedules(cfg)["j"].local_time == "08:17"


def test_load_schedules_invalid_cadence_raises(tmp_path) -> None:
    cfg = _write_schedules(tmp_path, "schedules:\n  j:\n    task_id: j\n    cadence: hourly\n")
    with pytest.raises(ConfigError):
        load_schedules(cfg)


def test_load_schedules_invalid_local_time_raises(tmp_path) -> None:
    cfg = _write_schedules(tmp_path, "schedules:\n  j:\n    task_id: j\n    local_time: '25:99'\n")
    with pytest.raises(ConfigError):
        load_schedules(cfg)


# ----------------------------------------------------------------------- is_due


def test_is_due_daily_always() -> None:
    s = TaskSchedule(task_id="j", cadence="daily")
    assert is_due(s, date(2026, 8, 10)) is True
    assert is_due(s, date(2026, 8, 11)) is True


def test_is_due_weekly_matches_weekday_only() -> None:
    s = TaskSchedule(task_id="j", cadence="weekly", weekday=1)  # 周一
    assert is_due(s, date(2026, 8, 11)) is True   # 2026-08-11 是周一
    assert is_due(s, date(2026, 8, 12)) is False  # 周二
    assert is_due(s, date(2026, 8, 16)) is False  # 周日


def test_is_due_monthly_matches_day() -> None:
    s = TaskSchedule(task_id="j", cadence="monthly", day=17)
    assert is_due(s, date(2026, 8, 17)) is True
    assert is_due(s, date(2026, 8, 16)) is False
    # 31 日在小月自动跳过（当月无 31 日）
    s31 = TaskSchedule(task_id="j", cadence="monthly", day=31)
    assert is_due(s31, date(2026, 8, 31)) is True
    assert is_due(s31, date(2026, 8, 30)) is False


# ------------------------------------------------------------------ SchedulerState


def test_state_load_missing_is_empty(tmp_path) -> None:
    state = SchedulerState.load(tmp_path / "nope.json")
    assert state.last_run == {}
    assert state.already_ran("t", date(2026, 8, 11)) is False


def test_state_save_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = SchedulerState()
    state.mark_ran("t", date(2026, 8, 11))
    state.save(path)
    loaded = SchedulerState.load(path)
    assert loaded.already_ran("t", date(2026, 8, 11)) is True
    assert loaded.already_ran("t", date(2026, 8, 12)) is False


def test_state_load_corrupt_returns_empty(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    assert SchedulerState.load(path).last_run == {}


# ---------------------------------------------------------------------- Scheduler


def _mock_task(task_id: str = "weekly_job") -> TaskConfig:
    return TaskConfig(id=task_id, topic_id="t1", enabled=True)


@contextmanager
def _patched_run_due(
    tmp_path: Path,
    schedules: str = WEEKLY_YAML,
    *,
    returncode: int = 0,
    run_side_effect=None,
):
    """构造 Scheduler 并 patch subprocess.run 与 load_task；yield (scheduler, fake_proc)。"""
    cfg = _write_schedules(tmp_path, schedules)
    scheduler = Scheduler(
        config_dir=cfg,
        project_root=tmp_path,
        state_path=tmp_path / "state.json",
        output="data/collection.jsonl",
        db_path="data/state/industry_intelligence.sqlite",
    )
    fake_proc = mock.Mock(returncode=returncode)
    with mock.patch(
        "industry_intelligence.ops.scheduler.subprocess.run",
        side_effect=run_side_effect,
        return_value=fake_proc,
    ) as run_mock, mock.patch(
        "industry_intelligence.config.loader.load_task",
        return_value=_mock_task(),
    ):
        yield scheduler, run_mock


def test_list_due_respects_state_and_force(tmp_path) -> None:
    cfg = _write_schedules(tmp_path)
    scheduler = Scheduler(config_dir=cfg, project_root=tmp_path, state_path=tmp_path / "s.json")
    today = date(2026, 8, 11)  # 周一 → weekly(weekday=1) 到期
    assert scheduler.list_due(today) == ["weekly_job"]
    # 标记今天已运行后不再列出
    state = SchedulerState()
    state.mark_ran("weekly_job", today)
    state.save(tmp_path / "s.json")
    assert scheduler.list_due(today) == []
    assert scheduler.list_due(today, force=True) == ["weekly_job"]


def test_list_due_only_ignores_cadence(tmp_path) -> None:
    cfg = _write_schedules(tmp_path)
    scheduler = Scheduler(config_dir=cfg, project_root=tmp_path, state_path=tmp_path / "s.json")
    # 周二（weekly 不到期），但 only 指定 → 仍列出
    assert scheduler.list_due(date(2026, 8, 12), only="weekly_job") == ["weekly_job"]


def test_run_due_success_marks_state_and_skips_next(tmp_path) -> None:
    today = date(2026, 8, 11)
    with _patched_run_due(tmp_path) as (scheduler, proc):
        result = scheduler.run_due(today)
    assert result.ran == ["weekly_job"]
    assert result.failed == []
    # subprocess 收到的命令含完整链路标志
    args = proc.call_args.args[0]
    assert "--phase2" in args and "--phase3" in args and "--phase4" in args
    assert "--output" in args and "--db-path" in args
    # 状态已记录 → 同一天再次 run_due 跳过
    with _patched_run_due(tmp_path) as (scheduler2, _proc2):
        result2 = scheduler2.run_due(today)
    assert result2.skipped == ["weekly_job"]
    assert result2.ran == []


def test_run_due_retry_succeeds_on_second_attempt(tmp_path) -> None:
    calls: list[int] = []

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(1)
        return mock.Mock(returncode=0 if len(calls) > 1 else 1)

    with _patched_run_due(tmp_path, run_side_effect=fake_run) as (scheduler, _proc):
        result = scheduler.run_due(date(2026, 8, 11), retry=1)
    assert len(calls) == 2
    assert result.ran == ["weekly_job"]
    assert result.failed == []


def test_run_due_failure_reported(tmp_path) -> None:
    with _patched_run_due(tmp_path, returncode=1) as (scheduler, _proc):
        result = scheduler.run_due(date(2026, 8, 11), retry=0)
    assert result.ran == []
    assert result.failed == ["weekly_job"]
    # 失败不写状态 → 当天可重跑
    with _patched_run_due(tmp_path, returncode=1) as (scheduler2, _proc2):
        result2 = scheduler2.run_due(date(2026, 8, 11), retry=0)
    assert result2.failed == ["weekly_job"]
