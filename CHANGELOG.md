# CHANGELOG

## v0.4.0a1 — 2026-08-11

### Phase 3：竞争情报分析

- **分析数据模型**：`analysis/models.py` — `Claim` / `ClaimEvidence` / `IndexScore` / `TrendIndicator` / `AnalysisResult`；确定性 `claim_id`（sha256(文本|维度|run)[:16]）；`claim_type` / `evidence_role` 取值与 SQLite CHECK 一致。
- **配置扩展**：`system.yaml` 启用 `analysis`（启用维度 / 比较窗口 / 置信度门槛）与 `report`（Phase 4 用）段；`config/models.py` 新增 `AnalysisConfig`、`ReportConfig`。
- **SQLite 扩展**：新增 `claims` / `claim_evidence` 两表（证据链可追溯，CHECK 强制 document_id 或 observation_id 至少其一）；`query_events_in_range` / `query_observations_in_range` / `query_events_by_entity` / `count_events_by_type` 等历史查询方法；runs 表记录 `analysis_claims` / `evidence_coverage`。
- **4 个分析师 Agent**：`analysis/{competitor,market,technology,risk}.py` — LLM 结构化输出合成结论 + 确定性内部指数（CAI 竞争活动度 / MMI 市场动量 / THI 技术热度 / RSI 风险信号），指数纯 SQL 聚合 + 权重公式，无 LLM 也可计算。
- **证据链保证**：分析师过滤 LLM 引用的证据 ID（valid 集合）+ 窗口真实文档兜底，每条 Claim 至少一条 Evidence。
- **历史比较**：`analysis/historical.py` — 5 个比较窗口（current/last/4w/12w/52w）+ 7 项趋势指标三点比较（事件流速 / 声量占比 / 重大项目增长 / 技术热度 / 价格 / 渠道 / 风险频次）。
- **汇聚引擎**：`analysis/engine.py` — 编排全部启用维度（独立失败不中断）、持久化 Claim/Evidence、计算证据覆盖率（有证据 Claim / 全部 Claim）。
- **Pipeline / CLI**：`--phase3`（需同时指定 `--phase2`）注入 `AnalysisEngine`；`RunResult` 增加 `analysis_results` / `analysis_claims` / `evidence_coverage` / `trends`；`--validate` 校验分析维度。
- **测试**：新增 ~100 个测试（分析模型 / 基类 / 4 分析师 / 历史比较 / 汇聚引擎单测 + Phase 3 端到端集成测试，全离线 mock）。

## v0.3.0a1 — 2026-08-11

### Phase 2：事件与指标抽取

- **LLM 接入**：`llm/provider.py`（`LLMProvider` ABC + `LLMError`）、`llm/deepseek_provider.py`（OpenAI SDK → DeepSeek base_url，API Key 环境变量注入，未设时抛 `LLMError`，测试用 mock）、`llm/prompts.py`（`config/prompts/` 模板加载）。
- **配置扩展**：`system.yaml` 启用 `llm` 段；`config/models.py` 新增 `LLMConfig`；`config/loader.py` 新增 `load_event_types()`（20 类事件分类法）。
- **实体解析**：`entities/resolver.py` — casefold 索引（canonical_name + aliases），文档标题/正文匹配并填充 `matched_entities`，同实体取最长命中词条。
- **事件分类**：`intelligence/classifier.py` — LLM 结构化输出主路径 + 关键词回落表（`topic.keywords.events` → event_type_id）。
- **事件聚类**：`intelligence/clustering.py` — 标题相似度（SequenceMatcher > 0.6）+ 共享实体 + 时间 ≤ 3 天，union-find 连通分量归并。
- **观测抽取**：`metrics/extractor.py` — JSON Schema 结构化抽取（仅显式数值），置信度 < 0.5 过滤，确定性 `observation_id`。
- **SQLite 查询层**：`storage/sqlite_store.py` — documents/entities/entity_aliases/events/event_documents/observations/runs 七表，WAL + 外键，参数化写入，`drop_all()` 可重建。
- **Pipeline**：`controller/pipeline.py` — Phase 1 + Phase 2 编排，单步失败不中断，`RunResult` 汇总，runs 表记录生命周期。
- **CLI**：新增 `--phase2 / --rebuild-db / --db-path`；版本升至 `0.3.0a1`。
- **测试**：新增 65 个测试（LLM / 实体 / 分类 / 聚类 / 观测 / SQLite 单测 + Phase 2 集成测试，全离线）。

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
