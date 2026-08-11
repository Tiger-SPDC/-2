"""运维与调度（Phase 5）：GitHub 全自动运行所需的通用调度器。

- ``scheduler.py``：读取 config/schedules.yaml，判断到期任务并调用 main.py 执行。
- 状态幂等：data/state/scheduler_state.json 记录上次运行日期，避免重复触发。
"""

from industry_intelligence.ops.scheduler import (
    DEFAULT_STATE_PATH,
    SCHEDULE_CADENCES,
    Scheduler,
    SchedulerResult,
    SchedulerState,
    TaskSchedule,
    is_due,
    load_schedules,
    today_in_timezone,
)

__all__ = [
    "SCHEDULE_CADENCES",
    "DEFAULT_STATE_PATH",
    "Scheduler",
    "SchedulerResult",
    "SchedulerState",
    "TaskSchedule",
    "is_due",
    "load_schedules",
    "today_in_timezone",
]
