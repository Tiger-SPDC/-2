"""Industry Intelligence Agent — 基础入口（Phase 0）。

本阶段仅作为项目 bootstrap 入口，不实现任何业务逻辑。
"""

from industry_intelligence.version import __version__


def main() -> None:
    """打印项目 bootstrap 信息。"""
    print("Industry Intelligence Agent")
    print("Project bootstrap initialized.")
    print("Current phase: Phase 0")
    print(f"Version: {__version__}")


if __name__ == "__main__":
    main()
