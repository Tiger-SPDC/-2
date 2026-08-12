"""推送内容日志 append_push_log 单元测试（全离线）。"""

from __future__ import annotations

import json

from industry_intelligence.notification.push_log import append_push_log


def test_append_creates_parent_dirs(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "nested" / "dir" / "push_log.jsonl"
    ok = append_push_log(path, {"run_id": "r1", "content": "摘要"})
    assert ok is True
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "run_id": "r1", "content": "摘要"
    }


def test_append_accumulates_multiple_records(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "push_log.jsonl"
    assert append_push_log(path, {"run_id": "r1", "success": True})
    assert append_push_log(path, {"run_id": "r2", "success": False, "error": "down"})
    lines = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["run_id"] for r in lines] == ["r1", "r2"]
    assert lines[1]["success"] is False
    assert lines[1]["error"] == "down"


def test_append_failure_returns_false(tmp_path) -> None:  # noqa: ANN001
    # 目标是一个已存在的目录 → 无法作为文件追加，返回 False 不抛出
    path = tmp_path / "already_dir"
    path.mkdir()
    assert append_push_log(path, {"run_id": "r1"}) is False
