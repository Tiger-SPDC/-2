"""Phase 0 bootstrap 基础测试（随 Phase 1 版本升级同步更新断言）。

验证：包可导入、版本号存在、main.py 基础入口可运行。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import industry_intelligence
from industry_intelligence.version import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_package_importable() -> None:
    assert industry_intelligence.__version__ == "0.4.0a1"


def test_version_exists() -> None:
    assert isinstance(__version__, str)
    assert __version__ == "0.4.0a1"


def test_main_entry_runs() -> None:
    # 子进程需要 src 在 sys.path 上（无需 pip install -e .）
    env = dict(os.environ)
    src = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py"), "--version"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "industry-intelligence-agent" in result.stdout
    assert "0.4.0a1" in result.stdout
