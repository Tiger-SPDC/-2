# CHANGELOG

## v0.7.0a7 — 2026-08-13

### 推送质量：未跟踪企业上屏 + 企业节不被截断

- **背景**：v0.7.0a6 GitHub 实跑确认热点行已入推送，但"企业竞争变化"节仍只显示跟踪企业（星星充电）——未跟踪但有动态的"蔚来"等因 LLM 分析师按旧 prompt 把 entity_id 留空、被归入"（未指定实体）"；且 600 字预算下 5 件事完整标题挤占企业节，被 `[已截断]` 切掉。
- **放宽实体标注**：4 个分析 prompt（competitor/market/technology/risk）的 entity_id 规则从"必须来自给定企业列表"放宽为"标注结论具体涉及的企业名（给定列表用 canonical_name，行业整体结论才留空）"，让采集数据中实际出现的未跟踪企业进入实体维度。
- **报告层实体归一化**：`ReportDataBuilder._canonicalize_entity()` 把 claim 的 entity_id 归一——命中跟踪企业别名（如"特来电新能源"）归一到 canonical_name，非跟踪企业信任原值；映射全部来自 TopicProfile 配置（零硬编码），避免企业节重复。
- **分节预算**：`DigestFormatter` 对一句话判断（≤50 字）、5 件事每条标题（≤30 字）、企业节每条动态（≤42 字）分别截断，保证企业节在 600 字内至少有空间展示有动态的企业；`_fit` 仍作为整体兜底。
- **测试**：digest 分节截断 + `_fit` 兜底 + builder 归一化（白盒边界 + 端到端）；全量 pytest / ruff / mypy 干净。

## v0.7.0a6 — 2026-08-12

### 推送反映 LLM 热点 + 企业节内容优先

- **背景**：用户反馈 v0.7.0a5 的推送（微信摘要）看不到 LLM 发现的热点内容，且"企业竞争变化"节仍显示无内容的跟踪企业"本期暂无动态"——热点只用于搜索、从不进入推送正文。
- **热点进入报表**：`ReportDataBundle.hot_topics` 新增字段，`ReportDataBuilder.build()` / `ReportEngine.run()` / Pipeline `_run_reporting` 三级透传 `RunResult.hot_topics`。
- **摘要顶部热点行**：`DigestFormatter` 周期行下方新增"本期热点关注：…"（最多 3 条，超长截断）；Markdown 执行摘要同步展示（最多 6 条）。
- **5 件事热点优先**：`_top5` 按事件标题/摘要是否命中热点短语优先排序（组内仍按日期倒序），热点为空时行为与 v0.7.0a5 完全一致。
- **企业节内容优先**：`_entity_changes` 重写——候选实体 = 跟踪企业 + 主张/事件中出现的企业（含比亚迪/蔚来等非跟踪企业），先列有实际动态的（最多 5 条）；有动态的不足 `_MIN_ENTITY_LINES=3` 条时才用跟踪企业"本期暂无动态"补足，避免空节但不让无内容企业占用位置。
- **测试**：digest 新增热点行 / 热点优先排序 / 非跟踪主张企业上屏 / 内容优先条数；builder hot_topics 透传；markdown 热点行；相关套件全过，ruff / mypy 干净。

## v0.7.0a5 — 2026-08-12

### LLM 动态热点发现 + 热点族优先检索

- **背景**：用户明确关键词（如"充电桩"）只是**大方向锚点**，检索不应依赖预先写死的固定对象（固定企业 × 固定事件词 × 固定官方域名 `site:`），而应在大方向之下**自己发现"当前最热门的话题"（热搜）再据此检索**。
- **HotTopicGenerator**：`intelligence/hot_topics.py` — 复用 EventClassifier 模式（provider + prompt_template 构造注入，LLMError 降级）。`generate(topic, focus=None, max_topics=10)` 把大方向词（core 或 `--focus` 覆盖）交给 DeepSeek，产出当前行业热点话题短语；无 provider / LLM 失败 / 非法结构 → 空列表。模板 `config/prompts/hot_topics.md`，行业内容运行时来自 Topic 配置，零行业硬编码。
- **热点族优先**：`SearchPlanner.generate_plans(topic, task, hot_topics=None)` — 热点短语非空时仅生成 `family="hot"` 查询（热点短语 × 地区，受 `QueryBudget.max_hot` 上限）；热点为空 / 组合为空时**回退固定三族**（既有行为完全不变）。两套装配（Pipeline `_collect` 与纯采集 CLI `_cmd_run`）同步接入。
- **门控联动（关键）**：`build_relevance_terms(topic, extra=())` 把当次热点短语并入相关性信号词，保证按热点检索到的文档不被 v0.7.0a3 门控误杀；Pipeline 与 `_cmd_run` 均以 `extra=hot` 构建 terms。
- **配置**：`CollectionConfig.hot_topics_enabled=True` / `hot_topics_max=10`（`config/system.yaml -> collection`）；`QueryBudget.max_hot=10`。关闭开关或热点为空即回退，运行不受影响。
- **可观测**：`RunResult.hot_topics` 记录当次热点；CLI 打印 `Hot topics (N): …` 与 planner 使用族（hot / fallback）。
- **测试**：新增 `test_hot_topic_generator.py`（降级/容错解析/schema/prompt）、`test_planner_hot.py`（热点族优先/截断/空回退/region 覆盖）、relevance extra 并入、pipeline 热点传参 + 合并门控、config loader 字段；376 全过，ruff / mypy 干净。

## v0.7.0a4 — 2026-08-12

### 推送内容日志

- **推送内容落日志**：`notification/push_log.py` 的 `append_push_log()` — 每次微信推送尝试（无论成败）向 `data/push_log.jsonl` 追加一条 JSONL 记录：时间戳 / run_id / topic_id / 通道 / 标题 / 是否成功 / 重试次数 / 错误 / **推送正文全文**。供事后追溯每次推送了什么内容、结果如何。
- **路径可配**：`StorageConfig.push_log_path`（`config/system.yaml -> storage.push_log_path`，默认 `data/push_log.jsonl`，与 `data/collection.jsonl` 一样随 GitHub 运行提交回仓库，本地与 GitHub 推送历史都可见）。
- **尽力而为**：日志写失败仅追加到 errors、不影响推送与报告；Pipeline `_run_notification` 在发送后统一落日志（成功与失败都记录）。
- **测试**：新增 `test_push_log.py`（建目录 / 累积追加 / 失败返回 False）+ Pipeline `_run_notification` 落日志集成测试（成功与失败各一条）+ 配置解析测试；355 全过，ruff / mypy 干净。

## v0.7.0a3 — 2026-08-12

### 推送内容相关性门控 + 企业节补足 5 条

- **采集层相关性门控**：`utils/relevance.py` — 由 Topic 配置关键词（core/products/market/technology，不含 events）与企业名/别名构建主题信号集；`is_doc_relevant()` 统一判定：websearch 等非 RSS 来源的文档须命中信号才进入事件/摘要（避免美国 runner Bing 返回的无关内容污染推送，如 Brisbane 旅游页），RSS 已由 feed 按查询词预过滤、`site:` 官方域结果按构造可信均直接放行。**采集两个入口同规则**：Pipeline `_collect`（--phase2+）与纯采集 CLI `_cmd_run`（--topic --task --output）都应用门控（实跑发现 `_cmd_run` 此前绕过门控，已修复并打印 filtered 计数）。
- **历史垃圾清理**：`SQLiteStore.purge_irrelevant_documents()` — 每次采集前清理库中不命中的 websearch 文档（按表依赖顺序删除，不触发外键 CHECK），并计入 `RunResult.documents_filtered`。
- **企业竞争变化 5 条**：`reporting/formatters/digest.py` 三节重写 —— 跟踪企业（Topic 配置的 5 家）全部输出，有动态的列主张/事件，无动态的以"本期暂无动态"补足，保证稳定 5 条；事件中出现但未跟踪的企业也纳入动态。
- **测试**：新增 `test_relevance.py`（信号构建/命中规则）、`test_pipeline_gate.py`（RSS/官方域放行 + websearch 门控 + 历史清理）、SQLite purge 测试、摘要企业节 5 条/主张优先/未跟踪实体测试；349 全过，ruff / mypy 干净。

## v0.7.0a2 — 2026-08-12

### 微信摘要结构调整（推送适配）

- **三节精简**：`reporting/formatters/digest.py` 由 6 节改为 3 节 —— 一、本周一句话判断；二、最重要的 5 件事；三、企业竞争变化。移除【四、关键数据】与【五、风险/机会】（推送条数受限导致内容冗余），【六、需要继续跟踪】一并移除。
- **字数收紧**：总字数（含标点）上限 800 → **600**。
- **链接兜底**：超长时只截正文（`_fit`），数据质量等级与完整报告链接始终保留，不再被截断吞掉。
- **测试**：结构断言改为 3 节（并断言 4/5/6 节不存在）、超长截断断言更新（`len ≤ 600` + 报告链接仍存在）；328 全过，ruff / mypy 干净。

## v0.7.0a1 — 2026-08-12

### 真实网页搜索（Bing SERP 爬取）+ 权威官方站点检索

- **WebSearchAdapter**：`sources/websearch_adapter.py` — 无 API Key、无账号，直接抓取 Bing SERP HTML 页。纯 stdlib `html.parser.HTMLParser` 解析 `<li class="b_algo">` 结果块（标题链接 + 摘要），过滤 Bing/Microsoft 内部链接；多 base_url 地理兜底（cn.bing.com → www.bing.com）；查询间礼貌 sleep + 失败退避重试。
- **官方站点 site: 限定检索**：`TopicProfile.official_domains`（config/topics/*.yaml，如 gov.cn/ndrc.gov.cn/miit.gov.cn/nea.gov.cn）→ `SearchPlanner` 生成 `"核心词 site:域名"` 查询族（family="official"），结果打 `official_domain` 标记供追溯。检索哪些官网由行业关键词决定，零行业硬编码。
- **CompositeAdapter**：`sources/composite_adapter.py` — 聚合 [RSS, WebSearch]，discover 跨源 URL 去重，fetch/parse/normalize 按 source_id 前缀路由；health_check = 任一子适配器健康。websearch 禁用/失败时优雅降级 RSS-only。
- **装配**：main.py `_build_adapter()` 替换两处硬编码 RSSAdapter，修掉 `if not feeds: return 0` 早退守卫；消费此前未用的 `polite_delay_seconds` / `retries` 配置。
- **配置**：`config/sources/search.yaml` 新增 `websearch:` 段（引擎参数，行业无关）；`QueryPlan.family` 查询族标记。
- **extra 追溯透传**：`ParsedDocument` / `NormalizedDocument` 增加 `extra` 字段并贯穿 parse→normalize→to_dict→from_dict 全链路（HTML/RSS/WebSearch 适配器），`official_domain` / `family` / `query_string` 等标记随文档持久化到 JSONL，供追溯"来自官方站点"的文档。
- **测试**：新增 34 个（SERP 解析 / 官方查询族 / 适配器 discover·限速·去重·base_url 兜底 / 组合路由·去重·健康检查 / 配置加载 / extra 全链路透传），全离线（file:// fixture + fetch/sleep mock）；328 全过，ruff / mypy 干净。
- **边界**：公开 HTML + 礼貌限速，不绕过登录/验证码/付费墙（docs/03 §8.5）。后续（V0.8+）再按需接入个别官网站内自建搜索。

## v0.6.1a1 — 2026-08-11

### 真实端到端验收修复（DeepSeek 集成）

- **模型修正**：`config/system.yaml` 默认模型改为账号实际可用的 `deepseek-v4-flash`（原 `deepseek-chat` 不存在）。`max_tokens` 4096 → 8192：deepseek-v4-flash 为推理模型，复杂分析 prompt（technology/review）会先消耗大量 `reasoning_tokens` 再产出内容，4096 会被推理耗尽导致空/截断 JSON。
- **结构化输出修正**：`llm/deepseek_provider.py` — DeepSeek 不支持 OpenAI 新版 `response_format={"type":"json_schema"}`（实测 400 "This response_format type is unavailable now"），改用 `json_object`；`json_object` 模式只检查 user 消息，user 不含 "json" 时自动补一句输出指令。`_request_json()` 空/非法 JSON 响应自动重试（3 次 + 2s 退避），缓解 deepseek-v4-flash 间歇性空内容（尤以长结构化输出为甚）。
- **分析师模板注入修复（关键）**：`analysis/base.py` 与 `analysis/review.py` — 此前 `_prompt_template` 加载后从未注入 LLM 请求，分析师只收到裸数据，模型回显输入结构而非 `{"claims":[...]}`。现在模板与数据合并进同一条 user 消息（与分类器/提取器的单条 user 成功模式一致），4 分析师 + Review Agent 全部按要求输出。
- **`_build_messages` 对齐**：AnalysisAgent 死代码方法同步为单条 user 合并模式，避免未来误用 system/user 分裂。
- **SQLite persist 修复（关键）**：`storage/sqlite_store.py` — `insert_document` / `insert_observation` 由 `INSERT OR REPLACE`（内部是 DELETE+INSERT）改为真正的 UPSERT（`ON CONFLICT DO UPDATE`）。此前重采集相同 `document_id` 时会触发 `claim_evidence.document_id ON DELETE SET NULL`，当 `observation_id` 也为空时违反 CHECK 约束（`document_id IS NOT NULL OR observation_id IS NOT NULL`）导致整轮 persist 报错。upsert 原地更新，证据链接保留，已用最小复现 + 回归测试锁定。
- **`.gitignore`**：补充 `*.sqlite-shm` / `*.sqlite-wal`（SQLite WAL 瞬态边车不提交）。
- **测试**：新增 4 个（`_build_messages` 无模板边界、`_generate_structured_safe` 模板合并、ReviewAgent 模板合并、文档重采集保留证据链接回归），同步模型与 `max_tokens` 断言；294 个测试全过，ruff / mypy 干净。
- **真实验证**：`charging_cn_weekly` 全链路 run 产出 22→24 条 Claim（100% 证据覆盖率）、4 分析师全部成功、Review 19 pass / 0 reject / 3 downgrade；0 观测为数据依赖（主题仅 5 家重点企业，本周大部分文档命中蔚来/比亚迪等未配置企业）。`persist: CHECK constraint failed` 错误已通过 UPSERT 修复后实跑确认消除；Review 偶发空响应（推理模型间歇性）在 3 次重试 + 退避后仍失败时按设计优雅降级（报告照常生成，该轮 Claim 标记为未审查）。
- **GitHub Actions 验收**：`grchuizi/-2` 仓库绑定 + Secrets（DEEPSEEK_API_KEY / SERVERCHAN_KEY，API 加密写入）+ push 后 Manual Run `fb94fbed3db94b29 [success]` — 50 doc / 25 Claim / 100% 证据覆盖 / Review 25 pass·0 reject·0 downgrade / **notified**（微信摘要推送成功）；数据与报告 auto-commit 回仓库，Artifact 上传；`scheduled_dispatcher` / `validation` / `maintenance` 工作流已随 main 生效（每日 08:17 北京时自动运行）。

## v0.6.0a1 — 2026-08-11

### Phase 5：GitHub 全自动运行

- **通用调度器**：`src/industry_intelligence/ops/scheduler.py` — 读取 `config/schedules.yaml`（cadence：daily/weekly/monthly + weekday/day + local_time + depth + notify），`is_due()` 纯确定性判定；`SchedulerState` 幂等状态（`data/state/scheduler_state.json`，已运行当天不重复触发，`--force` 可覆盖）；`Scheduler.run_due()` 依次调用 `main.py --phase2 --phase3 --phase4` 执行到期任务，失败自动重试（`--retry`）。
- **根级 CLI**：`scheduler.py` — `--dry-run` / `--run-due` / `--force` / `--retry N` / `--task <id>` / `--validate-schedules`；时区从 `system.yaml` 读取（IANA 解析失败退化为本地时区）。
- **CLI 覆盖参数**（manual_run 工作流支撑）：`main.py` 新增 `--days / --regions / --companies / --focus / --depth / --notify`，通过 `_apply_task_overrides()` patch 已解析的 Task 配置（不落库），供 GitHub Actions 手动触发时输入。
- **通知门修复**：Pipeline 现在强制执行 `task.output.notify`（为 false 时不推送微信，但报告照常生成）。
- **GitHub Actions 工作流**：`scheduled_dispatcher.yml`（每日北京 08:17 = UTC 00:17，跑 `scheduler.py --run-due`）、`manual_run.yml`（workflow_dispatch：task/topic/days/regions/companies/focus/depth/notify/force）、`validation.yml`（每日 `--validate` + `--validate-schedules`，失败微信告警）、`maintenance.yml`（每周 SQLite 完整性检查 + 清理 90 天前报告）。全部含 auto-commit（SQLite + JSONL + 报告 + 调度状态提交回仓库）、Artifact 上传、失败通知。
- **失败告警脚本**：`scripts/notify_failure.py`（复用 ServerChanAdapter，含 workflow run URL，永不抛出）、`scripts/maintenance.py`（`PRAGMA integrity_check` + 报告清理，DB 未生成不算失败）。
- **持久化提交策略**：`.gitignore` 放行 `data/state/industry_intelligence.sqlite`（跨运行积累的查询层是历史比较的事实源，必须提交回仓库）；JSONL 审计层与报告随运行提交。
- **Secrets**：GitHub Secrets `DEEPSEEK_API_KEY` / `SERVERCHAN_KEY`（映射到配置 `llm.api_key_env` / `notification.serverchan_key_env`），日志与报告不输出任何密钥。
- **测试**：新增 24 个（调度器 load/is_due 边界/状态幂等/run_due 命令构造与重试、CLI 覆盖参数、notify 门集成测试，全离线 mock）；版本升至 0.6.0a1。

## v0.5.0a1 — 2026-08-11

### Phase 4：质量审查 + 报告生成 + 通知推送

- **Review Agent**：`analysis/review.py` — 按 `config/prompts/review.md` 对全部分析 Claim + 证据执行 7 项检查（数字可追溯 / 日期 / 推断≠事实 / 活动度≠销量 / 证据 / 矛盾 / 措辞），输出 pass / reject / downgrade 结论并持久化到 `claim_reviews` 表；确定性 `review_id`（sha256(claim_id|verdict|run_id)[:16]）；无 provider 或关闭时返回空结果不报错。
- **配置扩展**：`system.yaml` 启用 `review`（enabled）与 `notification`（serverchan_key_env / retry / timeout_seconds）段；`config/models.py` 新增 `ReviewConfig`、`NotificationConfig`。
- **SQLite 扩展**：新增 `claim_reviews` 表（verdict / downgrade_to / issues / reason，CHECK 约束）；`insert_claim_review` / `query_claim_reviews` / `query_claims_with_evidence`（LEFT JOIN 合并 Claim + 证据）。
- **报告数据构建器**：`reporting/builder.py` — 纯确定性 SQLite 查询组装格式无关的 `ReportDataBundle`（events / observations / documents / companies / claims / indices / trends / review_results / quality）；数据质量指标（§25）确定性计算。
- **三种报告格式化器**：`reporting/formatters/` — `markdown.py`（15 节完整周报，`[事实]/[推断]/[预测]/[数据不足]` 标签，空节不虚构）、`excel.py`（8 个 Sheet 结构化导出，openpyxl 直接写入，不依赖 pandas）、`digest.py`（微信 6 节摘要 + 数据质量等级 + 报告路径，≤800 字）。
- **报告引擎**：`reporting/engine.py` — 按 `report_config` 开关渲染并写入 `{output_dir}/{run_id}/`；单格式失败不中断其它格式。
- **通知推送层**：`notification/adapter.py`（`NotificationAdapter` ABC）+ `serverchan.py`（`ServerChanAdapter`，POST `sctapi.ftqq.com`，内置重试，SendKey 环境变量注入，失败返回结果不抛出）。
- **Pipeline / CLI**：Pipeline 新增 Review → Reporting → Notification 三个独立 stage（各自 try/except，推送失败不回滚报告）；`RunResult` 增加 review 计数 / report_paths / digest_text / notification_sent；`--phase4`（需 `--phase2 --phase3`）与 `--report-dir`。
- **测试**：新增 46 个测试（ReviewAgent / 报告构建器 / 3 种格式化器 / 报告引擎 / ServerChan Adapter 单测 + Phase 4 端到端集成测试，全离线 mock）。

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
