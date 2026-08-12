"""推送内容日志（Phase 4）：每次推送尝试追加一条 JSONL 记录，供事后追溯。

无论推送成功与否都记录本次推送的内容（标题、正文、结果、通道、run_id）。
写日志是"尽力而为"——失败仅返回 False，不影响推送与报告生成。
"""

from __future__ import annotations

import json
from pathlib import Path


def append_push_log(path: str | Path, record: dict[str, object]) -> bool:
    """把一条推送记录追加写入 JSONL 日志。

    自动创建父目录；单条记录一行 JSON。写入失败返回 False，不抛出。
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 — 日志失败不影响推送
        return False
