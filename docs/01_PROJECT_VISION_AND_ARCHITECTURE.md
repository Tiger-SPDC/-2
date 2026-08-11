# 项目定位、使用方式、总体架构与目录规范

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

# 1. 项目总述

## 1.1 项目目标

本项目不是开发一个“充电桩爬虫”，而是建设一套可以长期复用、可切换研究主题、可持续积累历史数据的**通用产业竞争情报自动化 Agent**。

系统需要在无人值守或低人工干预条件下，完成以下闭环：

> 定时/手动触发 → 读取研究任务 → 自动规划检索 → 多源资料采集 → 清洗与去重 → 实体与事件识别 → 指标抽取 → 证据核验 → 历史数据库更新 → 竞争情报分析 → 周报/月报生成 → 微信推送 → 留存可追溯数据。

系统的长期目标不是“自动总结新闻”，而是形成一个具有连续历史记忆和证据链的产业情报系统，能够回答：

- 本周发生了什么重大事件？
- 哪些企业正在加速、收缩或改变战略？
- 哪些产品、技术、价格、渠道或区域出现显著变化？
- 哪些排名有可靠数据支持，哪些只能做活动度或趋势判断？
- 与过去 4 周、12 周、52 周相比，行业发生了哪些结构性变化？
- 哪些信息值得管理者、研究人员或投资决策者重点关注？
- 每一个结论的证据、来源、时间、可信度分别是什么？

## 1.2 核心设计原则

系统必须遵循以下原则：

1. **业务配置化**：主程序不得硬编码“充电桩”“户储”等行业词。
2. **主题可切换**：新增行业优先通过新增 Topic Profile 完成，而不是新建项目。
3. **任务可覆盖**：同一行业允许按品牌、地区、时间、指标、深度临时覆盖默认配置。
4. **数据与推断分离**：公开事实、企业自述、媒体报道、第三方估算、模型推断必须明确区分。
5. **证据优先于结论**：所有关键结论必须回链到证据；无证据不得生成确定性结论。
6. **可追溯**：保存 URL、标题、发布时间、抓取时间、原文摘要、内容指纹、来源等级和处理日志。
7. **历史可积累**：每次运行都要更新长期数据，而不是生成一次性报告后丢弃。
8. **可迁移**：GitHub 是首期运行环境，不应成为系统边界；未来可无痛迁移至云服务器、数据库或企业内部环境。
9. **插件化采集**：特殊网站通过 Source Adapter 接入，不污染核心流程。
10. **成本可控**：能用规则完成的任务不调用大模型；大模型按轻量抽取、深度分析分层调用。
11. **失败可诊断**：任何采集失败、模型失败、数据异常都必须形成可读日志与失败原因。
12. **合规采集**：遵守公开数据访问规则、robots、网站条款、访问频率限制，不绕过验证码、登录权限或付费墙。

## 1.3 首期不做的内容

V1 阶段明确不做：

- 不开发 Web 管理后台；
- 不开发桌面客户端；
- 不开发手机 APP；
- 不建设复杂微服务；
- 不上 Kubernetes；
- 不一开始就引入大型向量数据库；
- 不通过模拟登录控制个人微信；
- 不为所有网站写专用爬虫；
- 不生成没有可靠来源支撑的“销量榜”“市场份额榜”；
- 不把 AI 生成内容直接当成事实写入事实数据库。

---
# 2. 用户使用方式设计

## 2.1 使用模式 A：固定周期自动运行

示例：

- 任务：`charging_cn_weekly`
- 主题：中国充电基础设施
- 周期：每周一次
- 时间范围：过去 7 天
- 输出：微信摘要 + Markdown 完整周报 + 数据文件

运行过程由 GitHub Actions 自动触发，无需人工打开电脑。

## 2.2 使用模式 B：临时手动运行

用户进入 GitHub Actions，手动输入：

```text
topic_id      = home_storage
time_range    = 30d
regions       = Germany,Italy
companies     = Deye,Pylontech,Sungrow
focus         = shipment,price,inventory,channel
report_depth  = deep
```

系统即时按本次参数运行，但不改变默认每周任务。

> 注意：GitHub `workflow_dispatch` 的 choice 下拉项是写在 workflow YAML 中的静态选项。为了让新增 Topic 时不必修改 workflow，本系统 V1 建议使用字符串输入 `topic_id`，由程序验证该 Topic 是否存在，而不是将所有行业写死到下拉框。

## 2.3 使用模式 C：新增研究主题

例如新增“人形机器人关节模组”，只新增：

```text
config/topics/humanoid_joint.yaml
```

如果已有数据源适配器可以覆盖，则无需修改 Python 主程序。

## 2.4 使用模式 D：同一主题临时改变研究范围

例如默认户储研究全球市场，但某次只研究德国：

```yaml
topic_id: home_storage
overrides:
  regions: [Germany]
  time_range: 30d
  focus: [price, inventory, channel]
```

Topic Profile 不变，Task Config 仅覆盖本次运行。

## 2.5 使用模式 E：多主题并行运行

系统支持同时存在：

- 充电桩：周报；
- 户储：周报；
- 工商业储能：双周报；
- 固态电池：月报；
- 具身机器人：月报。

每个任务共用同一套采集、治理、分析、报告和通知引擎。

---
# 3. 总体系统架构

## 3.1 逻辑架构

系统按 12 个逻辑层组织：

1. **触发层 — GitHub Actions**：接收 `schedule` / `workflow_dispatch`，生成 `run_id` 与运行参数。
2. **控制层 — Task Controller**：读取 System Config、Topic、Task、Secrets、State，生成规范化任务上下文。
3. **规划层 — Search Planner**：根据行业词、企业、地区、时间和指标生成查询计划与查询预算。
4. **数据源层 — Source Manager**：根据 Query Plan 和 Source Registry 生成 URL/API/PDF/RSS 等采集任务。
5. **采集层 — Collection Engine**：下载与解析正文，记录元数据、抓取状态与内容指纹。
6. **治理层 — Data Governance**：完成去重、实体归一、Event、Observation 与 Evidence 构建。
7. **数据层 — Intelligence Data Layer**：将规范化事实持久化为 JSONL/CSV，并构建 SQLite 查询层。
8. **分析层 — Intelligence Agents**：结合当前周期与历史数据执行企业、市场、技术和风险分析。
9. **审核层 — Review Agent**：校验 Claim–Evidence、一致性、数值、时间和数据质量。
10. **报告层 — Report Engine**：生成 Markdown、Excel 与微信摘要。
11. **通知层 — Notification Layer**：通过 Server酱或其他 Adapter 发送报告和运行状态。
12. **持久化层 — Persistence**：提交新增数据、报告和 State，并保存必要 Artifact。

整体数据流：

```text
Trigger → Task/Topic → Search Plan → Sources → Documents →
Governance → Events/Metrics/Evidence → Historical Analysis →
Review → Report → WeChat → Persist
```

## 3.2 物理部署架构（V1）

V1 全部运行于一个 GitHub 仓库：

- GitHub Actions：执行环境；
- GitHub Secrets：API Key、推送 Token；
- GitHub Variables：非敏感运行参数；
- 仓库 Git 数据：配置、程序、结构化历史数据、报告；
- Actions Artifacts：一次运行产生的临时打包结果；
- SQLite：运行时查询和统计加速层，可由结构化数据重建。

### 为什么 SQLite 不作为唯一持久层

GitHub-hosted runner 是临时环境。如果把 `intelligence.db` 仅存在 runner 本地，运行结束后无法作为稳定长期状态。V1 采取：

> **JSONL/CSV/Parquet（可审计持久数据）为事实资产 → 每次运行重建/更新 SQLite → 报告和增量数据提交回私有仓库。**

这样后续迁移 PostgreSQL、DuckDB、对象存储时无需重新采集历史数据。

---
# 4. 项目目录规范

```text
industry-intelligence-agent/
│
├── .github/
│   └── workflows/
│       ├── scheduled_dispatcher.yml
│       ├── manual_run.yml
│       ├── validation.yml
│       └── maintenance.yml
│
├── config/
│   ├── system.yaml
│   ├── schedules.yaml
│   │
│   ├── topics/
│   │   ├── charging_pile.yaml
│   │   ├── home_storage.yaml
│   │   └── _template.yaml
│   │
│   ├── tasks/
│   │   ├── charging_cn_weekly.yaml
│   │   ├── home_storage_weekly.yaml
│   │   └── _template.yaml
│   │
│   ├── sources/
│   │   ├── search.yaml
│   │   ├── government.yaml
│   │   ├── media.yaml
│   │   ├── corporate.yaml
│   │   ├── tender.yaml
│   │   └── research.yaml
│   │
│   ├── taxonomies/
│   │   ├── event_types.yaml
│   │   ├── source_grades.yaml
│   │   └── metrics.yaml
│   │
│   └── prompts/
│       ├── extraction.md
│       ├── event_analysis.md
│       ├── competitor_analysis.md
│       ├── trend_analysis.md
│       ├── review.md
│       └── report.md
│
├── src/
│   ├── controller/
│   ├── planner/
│   ├── sources/
│   ├── collectors/
│   ├── parsers/
│   ├── governance/
│   ├── entities/
│   ├── metrics/
│   ├── storage/
│   ├── llm/
│   ├── analysis/
│   ├── review/
│   ├── reporting/
│   ├── notification/
│   └── common/
│
├── data/
│   ├── raw_index/
│   ├── documents/
│   ├── events/
│   ├── metrics/
│   ├── entities/
│   ├── claims/
│   ├── state/
│   └── db/
│       └── intelligence.db
│
├── reports/
│   ├── charging_pile/
│   └── home_storage/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── golden_reports/
│
├── scripts/
│   ├── validate_config.py
│   ├── rebuild_db.py
│   ├── export_excel.py
│   └── health_check.py
│
├── logs/
├── pyproject.toml
├── requirements.lock
├── README.md
└── main.py
```

### 目录约束

`src/` 中不得出现具体行业名称硬编码。行业知识必须放在 `config/topics/`、`config/taxonomies/` 或可插拔 Source Adapter 中。

---
