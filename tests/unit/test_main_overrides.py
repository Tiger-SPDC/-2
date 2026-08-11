"""main.py 覆盖参数单元测试（Phase 5 manual_run 工作流支撑，全离线）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main as main_cli  # noqa: E402
from industry_intelligence.config.models import (  # noqa: E402
    TaskConfig,
)


def test_apply_days() -> None:
    task = TaskConfig(id="t", topic_id="tp")
    main_cli._apply_task_overrides(task, days=30)
    assert task.window.days == 30


def test_apply_regions_companies_focus() -> None:
    task = TaskConfig(id="t", topic_id="tp")
    main_cli._apply_task_overrides(
        task,
        regions="中国, 德国",
        companies="特来电,星星充电",
        focus="充电桩",
    )
    assert task.overrides is not None
    # 逗号分隔 + 去空白
    assert task.overrides.regions == ["中国", "德国"]
    assert task.overrides.companies == ["特来电", "星星充电"]
    assert task.overrides.focus == ["充电桩"]


def test_apply_depth_and_notify() -> None:
    task = TaskConfig(id="t", topic_id="tp")
    main_cli._apply_task_overrides(task, depth="deep", notify="false")
    assert task.output.depth == "deep"
    assert task.output.notify is False


def test_apply_no_args_leaves_task_unchanged() -> None:
    task = TaskConfig(id="t", topic_id="tp")
    main_cli._apply_task_overrides(task)
    assert task.window.days == 7
    assert task.overrides is None
    assert task.output.notify is True
