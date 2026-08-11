"""维护脚本（Phase 5）：SQLite 健康检查 + 过期报告清理。

用法：
  python scripts/maintenance.py --prune-report-days 90
  python scripts/maintenance.py --db-path data/state/industry_intelligence.sqlite

健康检查失败返回退出码 1（供 GitHub 工作流触发失败告警）。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "state" / "industry_intelligence.sqlite"


def check_db(db_path: Path) -> list[str]:
    """运行 SQLite 完整性检查；返回错误列表（空 = 正常）。

    数据库尚未生成（仓库刚初始化、从未运行过）不算错误，仅打印提示，
    避免首周维护误报失败告警。
    """
    if not db_path.is_file():
        print(f"[maintenance] info: sqlite 尚未生成: {db_path}")
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        return [f"sqlite error: {exc}"]
    if not row or row[0] != "ok":
        return [f"integrity_check: {row}"]
    return []


def prune_reports(reports_dir: Path, keep_days: int) -> int:
    """删除修改时间早于 keep_days 天的报告子目录；返回删除数。"""
    if not reports_dir.is_dir():
        return 0
    now = datetime.now(UTC)
    removed = 0
    for entry in reports_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if (now - mtime).days > keep_days:
            shutil.rmtree(entry)
            removed += 1
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Industry Intelligence maintenance")
    parser.add_argument("--prune-report-days", type=int, default=90)
    parser.add_argument(
        "--db-path", default=str(DEFAULT_DB), help="SQLite 路径"
    )
    args = parser.parse_args(argv)

    errors = check_db(Path(args.db_path))
    removed = prune_reports(PROJECT_ROOT / "output" / "reports", args.prune_report_days)
    status = "ok" if not errors else "FAILED"
    print(f"[maintenance] integrity_check={status}; pruned {removed} report dir(s)")
    for err in errors:
        print(f"[maintenance] ! {err}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
