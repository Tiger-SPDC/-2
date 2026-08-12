# PROJECT_STATUS

- **Project:** Industry Intelligence Agent
- **Version:** v0.7.0a5
- **Date:** 2026-08-12
- **Current phase:** Phase 5（GitHub 全自动运行已实现，本地 + GitHub Actions 真实端到端验收全部通过——含微信推送；v0.7.0a1 新增真实网页搜索——Bing SERP 爬取 + 官方站点 site: 限定；v0.7.0a2 微信摘要精简为 3 节 + ≤600 字；v0.7.0a3 推送相关性门控——垃圾内容不进摘要，企业节稳定 5 条；v0.7.0a4 推送内容日志——每次推送落 data/push_log.jsonl；v0.7.0a5 LLM 动态热点发现——大方向词只是锚点，检索以 LLM 发现的当前行业热点为主、固定三族查询降级兜底）
- **Code implementation:** 配置加载 / 搜索计划（含官方站点查询族）/ RSS·HTML·WebSearch·Composite 采集（Bing SERP 爬取 + 权威官方域名 site: 限定，无 API Key）/ 去重 / JSONL 存储 / LLM 结构化分析（实体·事件·观测）/ SQLite 查询层 / Phase 3 竞争情报分析（4 分析师 + 内部指数 + 历史比较 + Claim 证据链）/ Phase 4（Review Agent 7 项检查 + Markdown·Excel·微信摘要报告 + 数据质量章节 + Server酱通知）/ Phase 5（通用调度器 + 4 个 GitHub Actions 工作流 + auto-commit + Artifact + 失败通知 + retry）/ CLI
- **Repository safety boundary:** Required
- **Preferred local Python:** 3.12 (3.11+ acceptable)
- **Primary coding agent:** Claude Code
- **Selected backend for coding stage:** DeepSeek V4 Flash
- **Production scheduler target:** GitHub Actions

## 已完成

- [x] V1.0 总体系统规划
- [x] Claude 项目级开发宪法
- [x] 文档拆分包
- [x] 环境隔离规则
- [x] 本机预检脚本
- [x] DeepSeek V4 Flash 项目级启动脚本
- [x] Phase 0：Git 仓库初始化
- [x] Phase 0：标准目录结构
- [x] Phase 0：`src/industry_intelligence` 包骨架与版本模块
- [x] Phase 0：`pyproject.toml`（pytest/ruff/mypy/coverage 配置）
- [x] Phase 0：`main.py` 基础入口
- [x] Phase 0：`.gitignore` 与 `.env.example`
- [x] Phase 0：README
- [x] Phase 0：基础测试 `tests/unit/test_bootstrap.py`
- [x] Phase 0：GitHub Actions CI（`ci.yml`）
- [x] Phase 1：配置数据模型与加载器（`config/{models,loader}.py`）
- [x] Phase 1：标准化文档与哈希工具（`core/document.py`、`utils/{url,hashing}.py`）
- [x] Phase 1：数据源适配器（`sources/adapter.py` + RSS/HTML 实现）
- [x] Phase 1：搜索计划生成（`collectors/planner.py`）
- [x] Phase 1：Layer 1 去重与 JSONL 存储（`normalization/dedup.py`、`storage/jsonl_store.py`）
- [x] Phase 1：具体配置（充电基础设施 Topic/Task + taxonomies）
- [x] Phase 1：CLI（`--version` / `--validate` / `--topic --task`）
- [x] Phase 1：测试套件（10 单元 + 1 整合，全离线）
- [x] Phase 2：LLM Provider 抽象 + DeepSeek 实现（`llm/`，API Key 环境变量注入）
- [x] Phase 2：配置扩展（`system.yaml` llm 段、`LLMConfig`、`load_event_types()`）
- [x] Phase 2：实体别名解析（`entities/resolver.py`）
- [x] Phase 2：事件分类与聚类（`intelligence/classifier.py` + `clustering.py`）
- [x] Phase 2：Observation 结构化抽取（`metrics/extractor.py`）
- [x] Phase 2：SQLite 七表查询层（`storage/sqlite_store.py`，可重建）
- [x] Phase 2：Pipeline 控制器（`controller/pipeline.py`，单步失败不中断）
- [x] Phase 2：CLI `--phase2 / --rebuild-db / --db-path`；版本 0.3.0a1
- [x] Phase 2：测试套件（+65 测试，全离线 mock）
- [x] Phase 3：分析数据模型与配置（`analysis/models.py`、`AnalysisConfig`/`ReportConfig`）
- [x] Phase 3：SQLite claims / claim_evidence 两表 + 历史窗口查询
- [x] Phase 3：4 分析师 Agent（Competitor / Market / Technology / Risk）+ 确定性指数 CAI / MMI / THI / RSI
- [x] Phase 3：历史比较 7 项趋势指标（`analysis/historical.py`）
- [x] Phase 3：汇聚引擎与证据覆盖率（`analysis/engine.py`）
- [x] Phase 3：Pipeline 注入与 CLI `--phase3`；版本 0.4.0a1
- [x] Phase 3：测试套件（+~100 测试，全离线 mock）
- [x] Phase 4：Review Agent（7 项检查 + pass/reject/downgrade，`claim_reviews` 表）
- [x] Phase 4：报告数据构建器（`ReportDataBundle` 格式无关中间层 + 数据质量指标）
- [x] Phase 4：Markdown 15 节完整周报格式化器
- [x] Phase 4：Excel 8-Sheet 结构化导出格式化器（openpyxl）
- [x] Phase 4：微信摘要格式化器（6 节 + 数据质量等级 + ≤800 字）
- [x] Phase 4：报告引擎（开关控制 + 单格式失败隔离，`output/reports/{run_id}/`）
- [x] Phase 4：通知推送层（`NotificationAdapter` ABC + `ServerChanAdapter`，SendKey 环境变量注入）
- [x] Phase 4：Pipeline 三 stage 集成（Review → Reporting → Notification）+ CLI `--phase4 / --report-dir`；版本 0.5.0a1
- [x] Phase 4：测试套件（+46 测试，全离线 mock）
- [x] Phase 5：通用调度器（`ops/scheduler.py` + 根级 `scheduler.py`，schedules.yaml / 幂等状态 / 失败重试）
- [x] Phase 5：CLI 覆盖参数（`--days/--regions/--companies/--focus/--depth/--notify`）+ notify 门修复
- [x] Phase 5：GitHub Actions 工作流（scheduled_dispatcher / manual_run / validation / maintenance，含 auto-commit + Artifact + 失败通知）
- [x] Phase 5：失败告警与维护脚本（notify_failure.py / maintenance.py）；`.gitignore` 放行积累数据提交；版本 0.6.0a1
- [x] Phase 5：测试套件（+24 测试，全离线 mock）
- [x] v0.6.1a1：DeepSeek 集成修复（json_schema→json_object、max_tokens 4096→8192 应对推理 token 饥饿、分析师/审查模板注入修复、多次重试 + 退避；294 测试 + ruff/mypy 干净）
- [x] v0.7.0a1：真实网页搜索（WebSearchAdapter，Bing SERP 爬取无 API Key）+ CompositeAdapter（RSS 基线并行、失败降级）+ 官方站点 site: 限定（TopicProfile.official_domains，检索哪些官网由行业关键词决定）+ QueryPlan 查询族标记；extra 追溯透传（official_domain/family 随文档持久化到 JSONL）；消费 polite_delay_seconds/retries；328 测试 + ruff/mypy 干净
- [x] v0.7.0a2：微信摘要精简为 3 节（一句话判断 / 最重要的 5 件事 / 企业竞争变化）+ 数据质量 + 完整报告，总字数 ≤600（含标点）；移除关键数据/风险机会/继续跟踪三节；超长只截正文、报告链接始终保留；328 测试 + ruff/mypy 干净
- [x] v0.7.0a3：推送相关性门控（websearch 非 RSS 来源须命中 Topic 关键词/企业名信号才进事件与摘要，避免美区 Bing 垃圾污染推送；采集前清理历史无关 websearch 文档，不触发外键 CHECK；`is_doc_relevant` 统一规则覆盖 Pipeline 与纯采集 CLI 两个入口）+ 企业竞争变化稳定 5 条（5 家跟踪企业全输出，无动态以"本期暂无动态"补足，事件中出现未跟踪企业也纳入）+ `documents_filtered` 运行指标；349 测试 + ruff/mypy 干净
- [x] v0.7.0a4：推送内容日志（每次微信推送尝试——无论成败——向 `data/push_log.jsonl` 追加时间戳/run_id/topic_id/通道/标题/结果/错误/推送正文全文，路径经 `storage.push_log_path` 可配，随 GitHub 运行提交回仓库；日志写失败不影响推送）；355 测试 + ruff/mypy 干净
- [x] v0.7.0a5：LLM 动态热点发现（`HotTopicGenerator` 用 DeepSeek 基于大方向词生成当前行业热点，`SearchPlanner` 热点族优先——热点短语 × 地区 family="hot"，热点为空回退固定三族；热点短语并入相关性门控信号词避免误杀；`CollectionConfig.hot_topics_enabled/max` 可配；`RunResult.hot_topics` 可观测；两套采集装配同步接入）；376 测试 + ruff/mypy 干净
- [x] 真实端到端验收（本地，DEEPSEEK_API_KEY）：`charging_cn_weekly` 全链路 run `9e6c7ad9041d4757 [success]` — 50 doc / 50 event / 23 Claim / 100% 证据覆盖率 / Review 18 pass·0 reject·5 downgrade，无错误；`persist: CHECK constraint failed`（INSERT OR REPLACE 触发外键 SET NULL）已修复实跑确认

## 已完成（GitHub 验收）

- [x] GitHub 远端仓库绑定：`origin` = `https://github.com/grchuizi/-2.git`，`main` 已推送
- [x] Secrets 配置：`DEEPSEEK_API_KEY` / `SERVERCHAN_KEY`（经 GitHub API + libsodium 加密设置，未落库、未提交）
- [x] GitHub Actions Manual Run 验收：Run `fb94fbed3db94b29 [success]` — 50 doc / 25 Claim / 100% 证据覆盖 / Review 25 pass·0 reject·0 downgrade / **notified**（微信摘要推送成功）；数据与报告 auto-commit 回仓库，Artifact 已上传
- [x] GitHub Actions Manual Run（v0.7.0a1 网页搜索）：Run `31557514525 [success]` — `data/collection.jsonl` 新增 13 条 `websearch:bing`（美区 runner 成功抓 Bing，family=company，extra 追溯正常）；`site:` 官方查询在美区 Bing 零结果属地理差异（本地中国网络命中 6 条 gov.cn）
- [x] GitHub Actions Manual Run（v0.7.0a2 摘要精简）：Run `31559108956 [success]` — 微信推送 `digest.txt` 实为 **581 字 ≤ 600**，3 节结构（一句话判断 / 最重要的 5 件事 / 企业竞争变化）+ 数据质量 + 完整报告；数据与报告 auto-commit 回仓库

## 尚未开始

- [ ] 官网站内自建搜索接入（V0.8+ 增强；V0.7 已用 Bing site: 限定覆盖权威官方域名）
- [ ] 采集规模扩大与运行调度优化
