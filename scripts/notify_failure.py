"""GitHub Actions 失败告警（Phase 5）：复用 ServerChanAdapter 推送失败消息。

环境变量：
  SERVERCHAN_KEY      Server酱 SendKey（GitHub Secret，日志不输出）
  GITHUB_REPOSITORY / GITHUB_RUN_ID / GITHUB_REF / GITHUB_WORKFLOW（Actions 自动注入）

本脚本永不抛出：告警失败只打印到 stderr，不掩盖原任务的失败状态。
"""

from __future__ import annotations

import os
import sys

# 兼容未安装包时直接运行脚本；GitHub Actions 中已 pip install -e .
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from industry_intelligence.notification import ServerChanAdapter  # noqa: E402


def build_content() -> str:
    """组装失败告警正文（仅元信息，不含任何 Secret）。"""
    repo = os.environ.get("GITHUB_REPOSITORY", "unknown/repo")
    run_id = os.environ.get("GITHUB_RUN_ID", "?")
    ref = os.environ.get("GITHUB_REF", "")
    workflow = os.environ.get("GITHUB_WORKFLOW", "")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    return "\n".join(
        [
            "产业情报 Agent 运行失败。",
            f"工作流：{workflow}",
            f"仓库：{repo}",
            f"Ref：{ref}",
            f"Run：{run_id}",
            f"详情：{run_url}",
            "",
            "请登录 GitHub Actions 查看日志与 Artifact。",
        ]
    )


def main() -> int:
    sendkey = os.environ.get("SERVERCHAN_KEY")
    adapter = ServerChanAdapter(sendkey=sendkey, retry=2)
    result = adapter.send("产业情报 Agent 运行失败", build_content())
    if not result.success:
        # 告警失败不抛出；打印便于排查（不含 Secret）
        print(f"[notify_failure] send failed: {result.error}", file=sys.stderr)
        return 1
    print("[notify_failure] failure alert sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
