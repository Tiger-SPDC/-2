# CHANGELOG

## v0.2.0a1 — 2026-08-11

### Phase 1：最小可用采集链路

- **配置层**：新增 `config/system.yaml`、`config/topics/`（模板 + 充电基础设施）、`config/tasks/`（模板 + 每周任务）、`config/sources/search.yaml`、`config/taxonomies/`（事件类型 / 源等级 / 指标）。
- **配置模型**：`src/industry_intelligence/config/{models,loader}.py` — 类型化 dataclass + YAML 加载与校验（错误信息含文件名与字段）。
- **文档与哈希**：`src/industry_intelligence/core/document.py`（`NormalizedDocument` + `to_dict/from_dict`）、`utils/url.py`（URL 规范化）、`utils/hashing.py`（sha256 前缀哈希）。
- **数据源适配器**：`sources/adapter.py`（`SourceAdapter` ABC）、`rss_adapter.py`（feedparser）、`html_adapter.py`（标签剥离），支持 `file://` 离线测试。
- **搜索计划**：`collectors/planner.py` — 核心词 × 企业/事件 × 地区，预算上限 + 指纹去重。
- **去重与存储**：`normalization/dedup.py`（Layer 1 内存去重）、`storage/jsonl_store.py`（追加式 JSONL，每次 flush）。
- **CLI**：`main.py` 新增 `--version` / `--validate` / `--topic --task`；版本升至 `0.2.0a1`。
- **测试**：10 个单元测试 + 1 个整合测试（全离线，file:// fixture）；Phase 0 测试同步更新版本断言。

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
