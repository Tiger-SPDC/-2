# CHANGELOG

## v0.1.0 — 2026-08-11

### Project bootstrap

- 初始化 Git 仓库与标准目录结构。
- 建立 `src/industry_intelligence` 包骨架（含 `version.py`，`__version__ = "0.1.0"`）。
- 新增 `pyproject.toml`（Python >= 3.11；dev 依赖：pytest / pytest-cov / ruff / mypy）。
- 新增 `main.py` 基础入口与 `README.md`。
- 更新 `.gitignore` 与 `.env.example`（仅变量名，无真实密钥）。
- 新增基础测试 `tests/unit/test_bootstrap.py`。
- 新增 GitHub Actions CI（`ci.yml`：push / pull_request → ruff → mypy → pytest）。
- 更新 `PROJECT_STATUS.md`。

## Preflight v1.0 — 2026-08-11

- 建立开发前准备包。
- 加入环境隔离、安全边界、Claude 宪法与规划拆分文档。
