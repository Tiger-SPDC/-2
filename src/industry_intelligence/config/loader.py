"""配置加载与验证：YAML → 类型化 dataclass。

错误信息包含文件名与缺失字段名，便于定位。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from industry_intelligence.config.models import (
    CollectionConfig,
    CompanyEntity,
    QualityConfig,
    StorageConfig,
    SystemConfig,
    TaskConfig,
    TaskOutput,
    TaskOverrides,
    TaskWindow,
    TopicEntities,
    TopicKeywords,
    TopicProfile,
    TopicScope,
)


class ConfigError(ValueError):
    """配置加载或验证失败。"""


def load_system_config(path: str | Path = "config/system.yaml") -> SystemConfig:
    """加载系统级配置。"""
    data = _read_yaml(path)
    return _parse_system_config(data, str(path))


def load_topic(topic_id: str, config_dir: str | Path = "config") -> TopicProfile:
    """按 topic_id 加载 config/topics/{topic_id}.yaml。"""
    path = Path(config_dir) / "topics" / f"{topic_id}.yaml"
    data = _read_yaml(path)
    return _parse_topic(data, topic_id, str(path))


def load_task(task_id: str, config_dir: str | Path = "config") -> TaskConfig:
    """按 task_id 加载 config/tasks/{task_id}.yaml。"""
    path = Path(config_dir) / "tasks" / f"{task_id}.yaml"
    data = _read_yaml(path)
    return _parse_task(data, task_id, str(path))


def resolve_task(task: TaskConfig, topic: TopicProfile) -> TaskConfig:
    """校验 Task-Topic 引用一致，并用 Topic 默认值填充缺省 override。"""
    if task.topic_id != topic.id:
        raise ConfigError(
            f"Task '{task.id}' references topic_id '{task.topic_id}' "
            f"but loaded topic is '{topic.id}'"
        )
    if task.overrides is not None:
        return task
    return TaskConfig(
        id=task.id,
        topic_id=task.topic_id,
        enabled=task.enabled,
        window=task.window,
        overrides=TaskOverrides(regions=list(topic.scope.regions)),
        output=task.output,
    )


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _read_yaml(path: str | Path) -> dict[str, object]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Config file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {p} must contain a YAML mapping")
    return data


def _mapping(data: dict[str, object], key: str, path: str) -> dict[str, object]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: '{key}' must be a mapping")
    return value


def _parse_system_config(data: dict[str, object], path: str) -> SystemConfig:
    sys_section = _mapping(data, "system", path)
    collection = _mapping(data, "collection", path)
    storage = _mapping(data, "storage", path)
    quality = _mapping(data, "quality", path)

    return SystemConfig(
        timezone=_as_str(sys_section.get("timezone"), "system.timezone", path),
        default_language=_as_str(
            sys_section.get("default_language"), "system.default_language", path
        ),
        collection=CollectionConfig(
            max_concurrency=_as_int(
                collection.get("max_concurrency"), "collection.max_concurrency", path
            ),
            request_timeout_seconds=_as_int(
                collection.get("request_timeout_seconds"),
                "collection.request_timeout_seconds",
                path,
            ),
            retries=_as_int(collection.get("retries"), "collection.retries", path),
            user_agent=_as_str(collection.get("user_agent"), "collection.user_agent", path),
            polite_delay_seconds=_as_float(
                collection.get("polite_delay_seconds"),
                "collection.polite_delay_seconds",
                path,
            ),
        ),
        storage=StorageConfig(
            persistent_format=_as_str(
                storage.get("persistent_format"), "storage.persistent_format", path
            ),
            save_raw_html=_as_bool(
                storage.get("save_raw_html"), "storage.save_raw_html", path
            ),
            save_text_snapshot=_as_bool(
                storage.get("save_text_snapshot"), "storage.save_text_snapshot", path
            ),
        ),
        quality=QualityConfig(
            require_evidence_for_key_claim=_as_bool(
                quality.get("require_evidence_for_key_claim"),
                "quality.require_evidence_for_key_claim",
                path,
            ),
            reject_untraceable_numbers=_as_bool(
                quality.get("reject_untraceable_numbers"),
                "quality.reject_untraceable_numbers",
                path,
            ),
        ),
    )


def _parse_topic(data: dict[str, object], topic_id: str, path: str) -> TopicProfile:
    topic_section = _mapping(data, "topic", path)
    tid = topic_section.get("id")
    if tid != topic_id:
        raise ConfigError(f"{path}: topic.id '{tid}' does not match filename '{topic_id}'")
    name = topic_section.get("name")
    version = topic_section.get("version")
    if not name:
        raise ConfigError(f"{path}: missing required field: topic.name")
    if not version:
        raise ConfigError(f"{path}: missing required field: topic.version")

    scope = _mapping(data, "scope", path)
    regions = _as_str_list(scope.get("regions"), "scope.regions", path)
    if not regions:
        raise ConfigError(f"{path}: missing required field: scope.regions")

    entities = _mapping(data, "entities", path)
    companies = _parse_companies(entities.get("companies"), path)

    keywords_raw = _mapping(data, "keywords", path)
    core_keywords = _as_str_list(keywords_raw.get("core"), "keywords.core", path)
    if not core_keywords:
        raise ConfigError(f"{path}: missing required field: keywords.core")

    return TopicProfile(
        id=str(tid),
        name=str(name),
        version=str(version),
        scope=TopicScope(
            regions=regions,
            default_window_days=_as_int(
                scope.get("default_window_days"), "scope.default_window_days", path
            ),
        ),
        entities=TopicEntities(companies=companies),
        keywords=TopicKeywords(
            core=core_keywords,
            products=_as_str_list(keywords_raw.get("products"), "keywords.products", path),
            market=_as_str_list(keywords_raw.get("market"), "keywords.market", path),
            technology=_as_str_list(keywords_raw.get("technology"), "keywords.technology", path),
            events=_as_str_list(keywords_raw.get("events"), "keywords.events", path),
            exclude=_as_str_list(keywords_raw.get("exclude"), "keywords.exclude", path),
        ),
        metrics=_as_str_list(data.get("metrics"), "metrics", path),
    )


def _parse_companies(raw: object, path: str) -> list[CompanyEntity]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: entities.companies must be a list")
    companies: list[CompanyEntity] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"{path}: entities.companies[{idx}] must be a mapping")
        canonical_name = item.get("canonical_name")
        if not canonical_name:
            raise ConfigError(f"{path}: entities.companies[{idx}] missing 'canonical_name'")
        companies.append(
            CompanyEntity(
                canonical_name=str(canonical_name),
                aliases=_as_str_list(
                    item.get("aliases"), f"entities.companies[{idx}].aliases", path
                ),
                priority=_as_int(
                    item.get("priority"), f"entities.companies[{idx}].priority", path
                ),
            )
        )
    return companies


def _parse_task(data: dict[str, object], task_id: str, path: str) -> TaskConfig:
    task_section = _mapping(data, "task", path)
    tid = task_section.get("id")
    if tid != task_id:
        raise ConfigError(f"{path}: task.id '{tid}' does not match filename '{task_id}'")
    topic_id = task_section.get("topic_id")
    if not topic_id:
        raise ConfigError(f"{path}: missing required field: task.topic_id")

    window = _mapping(data, "window", path)
    output = _mapping(data, "output", path)
    overrides_raw = data.get("overrides")
    if overrides_raw is not None and not isinstance(overrides_raw, dict):
        raise ConfigError(f"{path}: 'overrides' must be a mapping")

    return TaskConfig(
        id=str(tid),
        topic_id=str(topic_id),
        enabled=_as_bool(task_section.get("enabled"), "task.enabled", path),
        window=TaskWindow(
            type=_as_str(window.get("type"), "window.type", path),
            days=_as_int(window.get("days"), "window.days", path),
        ),
        overrides=_parse_overrides(overrides_raw),
        output=TaskOutput(
            depth=_as_str(output.get("depth"), "output.depth", path),
            notify=_as_bool(output.get("notify"), "output.notify", path),
        ),
    )


def _parse_overrides(raw: object) -> TaskOverrides | None:
    if raw is None:
        return None
    assert isinstance(raw, dict)  # 调用方已校验
    return TaskOverrides(
        regions=_as_optional_str_list(raw.get("regions"), "overrides.regions"),
        companies=_as_optional_str_list(raw.get("companies"), "overrides.companies"),
        focus=_as_optional_str_list(raw.get("focus"), "overrides.focus"),
    )


# ---------------------------------------------------------------------------
# 类型转换助手（错误信息含文件名与字段路径）
# ---------------------------------------------------------------------------


def _as_str(value: object, field: str, path: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ConfigError(f"{path}: field {field} must be a string")


def _as_int(value: object, field: str, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}: field {field} must be an integer")
    return int(value)


def _as_float(value: object, field: str, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}: field {field} must be a number")
    return float(value)


def _as_bool(value: object, field: str, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: field {field} must be a boolean")
    return value


def _as_str_list(value: object, field: str, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{path}: field {field} must be a list of strings")
    return [v.strip() for v in value if v.strip()]


def _as_optional_str_list(value: object, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"config: field {field} must be a list of strings")
    return [v.strip() for v in value if v.strip()]
