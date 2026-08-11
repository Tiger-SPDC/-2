"""配置加载器单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from industry_intelligence.config.loader import (
    ConfigError,
    load_system_config,
    load_task,
    load_topic,
    resolve_task,
)


def test_load_valid_topic(fixtures_dir: Path) -> None:
    topic = load_topic("valid_charging_pile", config_dir=fixtures_dir)
    assert topic.id == "valid_charging_pile"
    assert topic.name == "充电基础设施（测试）"
    assert topic.scope.regions == ["中国"]
    assert [c.canonical_name for c in topic.entities.companies] == ["特来电", "星星充电"]
    assert topic.keywords.core == ["充电桩", "充电基础设施"]
    assert topic.metrics == ["station_count", "charger_count"]


def test_load_invalid_topic_raises(fixtures_dir: Path) -> None:
    with pytest.raises(ConfigError, match="keywords.core"):
        load_topic("invalid_topic", config_dir=fixtures_dir)


def test_load_missing_topic_raises(fixtures_dir: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_topic("no_such_topic", config_dir=fixtures_dir)


def test_load_valid_task(fixtures_dir: Path) -> None:
    task = load_task("valid_weekly", config_dir=fixtures_dir)
    assert task.id == "valid_weekly"
    assert task.topic_id == "valid_charging_pile"
    assert task.enabled is True
    assert task.window.days == 7


def test_load_task_with_overrides(fixtures_dir: Path) -> None:
    task = load_task("task_with_overrides", config_dir=fixtures_dir)
    assert task.overrides is not None
    assert task.overrides.regions == ["长三角"]
    assert task.overrides.companies == ["特来电"]
    assert task.overrides.focus == ["超充"]
    assert task.output.depth == "quick"


def test_resolve_task_fills_regions(fixtures_dir: Path) -> None:
    topic = load_topic("valid_charging_pile", config_dir=fixtures_dir)
    task = load_task("valid_weekly", config_dir=fixtures_dir)
    resolved = resolve_task(task, topic)
    assert resolved.overrides is not None
    assert resolved.overrides.regions == ["中国"]  # 由 topic.scope.regions 填充
    assert resolved.overrides.companies is None
    assert resolved.overrides.focus is None


def test_resolve_task_mismatched_topic_raises(fixtures_dir: Path) -> None:
    topic = load_topic("valid_charging_pile", config_dir=fixtures_dir)
    task = load_task("task_with_overrides", config_dir=fixtures_dir)
    assert task.topic_id == "valid_charging_pile"  # 先确认本身匹配
    mismatch = task.__class__(
        id="task_with_overrides",
        topic_id="other_topic",
        enabled=True,
    )
    with pytest.raises(ConfigError, match="topic_id"):
        resolve_task(mismatch, topic)


def test_load_system_config(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.timezone == "Asia/Shanghai"
    assert cfg.default_language == "zh-CN"
    assert cfg.collection.max_concurrency == 5
    assert cfg.storage.persistent_format == "jsonl"


def test_load_llm_config_section(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.llm.provider == "deepseek"
    assert cfg.llm.model == "deepseek-v4-flash"
    assert cfg.llm.api_key_env == "DEEPSEEK_API_KEY"
    assert cfg.llm.base_url == "https://api.deepseek.com/v1"
    assert cfg.llm.temperature == 0.1
    assert cfg.llm.max_tokens == 8192


def test_load_analysis_config(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.analysis.enabled_dimensions == [
        "competitor",
        "market",
        "technology",
        "risk",
    ]
    assert cfg.analysis.comparison_windows == [1, 4, 12, 52]
    assert cfg.analysis.confidence_threshold == 0.5


def test_load_report_config(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.report.markdown is True
    assert cfg.report.excel is True
    assert cfg.report.wechat_digest is True


def test_load_review_config(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.review.enabled is True


def test_load_notification_config(project_root: Path) -> None:
    cfg = load_system_config(project_root / "config" / "system.yaml")
    assert cfg.notification.serverchan_key_env == "SERVERCHAN_KEY"
    assert cfg.notification.retry == 2
    assert cfg.notification.timeout_seconds == 10


def test_load_event_types(project_root: Path) -> None:
    from industry_intelligence.config.loader import load_event_types

    event_types = load_event_types(project_root / "config")
    assert "other" in event_types
    assert len(event_types) == 20
