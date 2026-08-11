# 通用产业竞争情报自动化 Agent
## 完整规划与系统设计说明书（V1.0）

**项目定位：** Industry Intelligence Agent（通用产业竞争情报自动化系统）  
**首个试验主题：** 中国充电基础设施 / 充电桩产业  
**第二验证主题：** 户用储能设备  
**首期运行环境：** GitHub Actions  
**首期交付形态：** 无网站、无独立软件，以配置文件 + 自动化工作流 + Markdown/Excel/SQLite/微信推送为核心  
**文档日期：** 2026-08-11  
**版本：** V1.0  

---

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

# 5. 配置体系设计

# 5.1 System Config：系统级配置

负责与行业无关的系统行为。

示例：

```yaml
system:
  timezone: Asia/Shanghai
  default_language: zh-CN
  run_mode: production

storage:
  persistent_format: jsonl
  sqlite_rebuild: true
  save_raw_html: false
  save_text_snapshot: true

collection:
  max_concurrency: 5
  request_timeout_seconds: 20
  retries: 2
  user_agent: industry-intelligence-agent
  polite_delay_seconds: 1.5

llm:
  provider: configurable
  extraction_model: ${LLM_EXTRACTION_MODEL}
  analysis_model: ${LLM_ANALYSIS_MODEL}
  review_model: ${LLM_REVIEW_MODEL}

report:
  markdown: true
  excel: true
  wechat_digest: true

quality:
  require_evidence_for_key_claim: true
  reject_untraceable_numbers: true
  prohibit_inferred_ranking_as_fact: true
```

# 5.2 Topic Profile：行业长期知识包

Topic Profile 负责定义：

- 行业名称与范围；
- 企业与品牌；
- 实体别名；
- 核心关键词；
- 产品词；
- 技术词；
- 市场指标；
- 排除词；
- 地区；
- 事件类型偏好；
- 重点数据源；
- 分析维度；
- 行业特有单位与指标定义。

示例：

```yaml
topic:
  id: home_storage
  name: 户用储能设备
  version: 1.0

scope:
  regions: [China, Germany, Italy, UK, USA, South_Africa]

entities:
  companies:
    - canonical_name: 德业股份
      aliases: [德业, Deye]
      priority: 1
    - canonical_name: 派能科技
      aliases: [派能, Pylontech]
      priority: 1

keywords:
  core: [户储, 户用储能, 家庭储能, residential energy storage]
  products: [储能一体机, 储能逆变器, 电池包, PACK, ESS]
  market: [出货量, 市占率, 销量, 排名, 渠道, 库存, 价格]
  technology: [LFP, 磷酸铁锂, 高压户储, 低压户储, 混合逆变器]
  events: [发布, 中标, 签约, 合作, 扩产, 投资, 融资, 并购, 召回]
  exclude: [云存储, 手机存储, 数据存储]

metrics:
  - shipment
  - market_share
  - price
  - capacity
  - channel_inventory
  - dealer_expansion
  - new_product
  - certification

analysis:
  competitor_tracking: true
  market_trend: true
  technology_trend: true
  pricing_analysis: true
  policy_analysis: true
  risk_analysis: true
  opportunity_analysis: true
```

# 5.3 Task Config：具体运行任务

Task Config 只描述“这一次/这个周期要做什么”。

```yaml
task:
  id: home_storage_de_it_monthly
  topic_id: home_storage
  enabled: true

schedule:
  cadence: monthly
  day: 1
  local_time: "08:17"

window:
  type: rolling
  days: 30

overrides:
  regions: [Germany, Italy]
  companies: [德业股份, 派能科技, 阳光电源]
  focus: [shipment, price, inventory, channel]

output:
  depth: deep
  notify: true
```

# 5.4 Source Config：数据源注册表

每个数据源记录：

- source_id；
- 名称；
- 类型；
- 来源等级；
- 是否需要登录；
- 是否允许自动访问；
- 访问方式；
- 频率限制；
- 解析器；
- 适用主题；
- 失败降级策略。

```yaml
source:
  id: example_official_source
  type: official
  trust_grade: A
  adapter: html
  enabled: true
  rate_limit_per_minute: 10
  applicable_topics: [charging_pile, home_storage]
```

---

# 6. GitHub Actions 运行设计

## 6.1 定时调度策略

为避免每新增一个 Topic 就修改 cron，V1 采用**通用调度器**：

```text
GitHub Actions 每日固定时间触发一次
        ↓
scheduler.py 读取 schedules.yaml
        ↓
判断今天哪些任务到期
        ↓
依次执行到期任务
```

推荐调度时间避开整点，例如 08:17，而不是 08:00。GitHub 官方说明 scheduled workflow 在高负载时可能延迟，整点属于典型高负载时段。

对于产业周报这种非实时任务，允许数分钟级延迟，不追求证券交易级实时性。

## 6.2 手动触发

`manual_run.yml` 使用 `workflow_dispatch`，支持输入：

```text
topic_id
period_days
regions
companies
focus
report_depth
notify
```

这些输入在程序层校验，而不是在 workflow 层写死业务规则。

## 6.3 GitHub Secrets

必须进入 Secrets 的字段包括：

```text
LLM_API_KEY
SEARCH_API_KEY
SERVERCHAN_SENDKEY
PROXY_TOKEN（如未来需要）
PRIVATE_SOURCE_TOKEN（如未来合法接入）
```

不得提交到仓库、日志、配置样例或 Markdown 报告。

## 6.4 GitHub Variables

非敏感参数可放 Variables，例如：

```text
DEFAULT_TOPIC
DEFAULT_TIMEZONE
MAX_CONCURRENCY
REPORT_LANGUAGE
LOG_LEVEL
```

## 6.5 GitHub Artifact 的定位

Artifact 用于：

- 保存本次运行完整压缩包；
- 保存调试日志；
- 保存临时报表；
- 在任务间传递中间文件。

Artifact 不作为唯一长期数据库，因为其保留期可配置且受仓库策略限制。

## 6.6 自动提交策略

成功运行后，只将以下内容提交回仓库：

- 新增/更新后的规范化 JSONL/CSV 数据；
- 报告；
- 状态文件；
- 轻量统计索引。

原则上不提交：

- API Key；
- 大量原始网页；
- 临时缓存；
- 浏览器缓存；
- 调试截图；
- 含隐私或受限内容的抓取副本。

---

# 7. Search Planner：自动检索规划

## 7.1 目标

Search Planner 不直接“搜新闻”，而是将 Topic 和 Task 转换成一组可追踪、可重复的搜索计划。

## 7.2 查询维度

自动组合：

1. 行业核心词；
2. 企业/品牌；
3. 产品；
4. 事件词；
5. 指标词；
6. 地区；
7. 时间范围；
8. 技术词；
9. 排除词。

示例：

```text
德业 户储 德国 渠道 库存 最近30天
派能科技 户用储能 出货量 德国 2026
户储 价格 下调 欧洲 经销商
```

## 7.3 查询预算

为控制成本，每个任务设置：

- 最大查询数；
- 每个企业最大查询数；
- 每类事件最大查询数；
- 搜索结果最大数量；
- 高优先级实体额外预算。

## 7.4 Query Fingerprint

每条搜索计划生成指纹，避免同一次运行重复搜索完全相同的组合。

---

# 8. 数据源体系与采集插件

## 8.1 来源分层

推荐统一等级：

- **A**：政府、监管、官方统计、正式法规；核心事实优先。
- **A-/B+**：行业协会、交易平台、权威公共数据库；主要用于市场指标与行业数据。
- **B**：上市公司公告、财报、公司正式新闻稿；属于企业一手事实，但要识别企业自述偏差。
- **B-/C+**：高质量财经/产业媒体；用于事件补充与交叉验证。
- **C**：一般媒体、专业垂直网站；主要用于线索发现。
- **D**：自媒体、论坛、社交内容；只作为线索，不直接支持关键事实。
- **E**：无法识别来源或二次转述；默认排除或低权重。
- **F**：模型推断/估算；只能作为推断，绝不能伪装成事实。

## 8.2 Adapter 接口

统一 Source Adapter 接口：

```python
class SourceAdapter:
    def discover(self, query, context): ...
    def fetch(self, item): ...
    def parse(self, raw): ...
    def normalize(self, parsed): ...
    def health_check(self): ...
```

## 8.3 V1 优先支持的 Adapter

1. Search Adapter：搜索发现；
2. RSS Adapter：稳定低成本；
3. Static HTML Adapter：普通网页；
4. JSON/API Adapter：公开 API；
5. PDF Adapter：公告、政策、研究报告；
6. Browser Adapter：只有 JS 渲染确有必要时才用 Playwright；
7. Corporate Disclosure Adapter：企业公告类；
8. Tender Adapter：招投标类，按合法公开访问能力逐步增加。

## 8.4 降级策略

若某网站失败：

```text
专用 API → RSS → 静态 HTML → 搜索缓存/摘要 → 浏览器 → 标记失败
```

不会因为单一网站失败导致整个周报中断。

## 8.5 不做的绕过行为

- 不自动破解验证码；
- 不绕过登录；
- 不绕过付费墙；
- 不规避明显反爬限制；
- 不伪造登录态；
- 不高频并发攻击式请求。

如关键数据只能通过受限来源获得，应转为人工授权、合法 API 或商业数据源接入。

---

# 9. 文档处理与标准化

每条文档至少生成以下标准字段：

```text
document_id
canonical_url
source_id
title
published_at
fetched_at
author
language
content_text
summary
content_hash
url_hash
source_grade
topic_id
matched_entities
matched_keywords
raw_type
parser_version
```

## 9.1 时间标准化

同时保存：

- `published_at`：原文发布时间；
- `fetched_at`：系统抓取时间；
- `period_start/period_end`：指标所属周期。

不得把“抓取时间”误当成“事件发生时间”。

## 9.2 正文提取

优先提取正文，剔除：

- 导航；
- 推荐阅读；
- 评论；
- 页脚；
- 广告；
- 重复版权信息。

原始 URL 与文本快照必须保留映射关系。

---

# 10. 去重、聚类与事件合并

## 10.1 三层去重

### 层 1：完全重复

- URL 归一化；
- 文本 hash；
- 标题 hash。

### 层 2：转载重复

根据：

- 标题相似度；
- 关键实体；
- 时间接近度；
- 关键数字；
- 正文相似度。

### 层 3：同一事件多源报道

多个文章合并为一个 Event：

```text
Event
 ├─ 官方来源
 ├─ 媒体来源 1
 ├─ 媒体来源 2
 └─ 行业来源
```

最终分析以“事件”为单位，而不是以“文章数量”为单位。

## 10.2 事件聚类要求

事件聚类后必须保留全部 supporting documents，避免去重后丢失交叉验证信息。

---

# 11. 实体体系设计

## 11.1 实体类型

V1 支持：

- company；
- brand；
- product；
- technology；
- region；
- organization；
- policy；
- project；
- person（低优先级）；
- metric。

## 11.2 企业别名归一

示例：

```text
Deye / 德业 / 德业股份
          ↓
canonical_entity_id = company_deye
```

避免同一企业被统计成多个对象。

## 11.3 实体关系

长期可以积累：

```text
公司 → 品牌
公司 → 产品
公司 → 合作伙伴
公司 → 项目
公司 → 地区
公司 → 技术路线
公司 → 渠道
公司 → 投资/并购对象
```

V1 先用关系表实现，不急于上图数据库。

---

# 12. 事件分类体系

通用事件一级分类建议：

1. 战略调整；
2. 新产品/产品升级；
3. 技术研发；
4. 产能建设；
5. 投资扩产；
6. 融资；
7. 并购；
8. 中标/订单；
9. 合作/签约；
10. 渠道扩张；
11. 海外拓展；
12. 价格变化；
13. 市场/销量/出货；
14. 政策与监管；
15. 财务表现；
16. 供应链变化；
17. 召回/事故/质量；
18. 人事变动；
19. 诉讼/合规；
20. 其他。

Topic Profile 可以追加行业特有二级分类，例如充电桩的 V2G、液冷超充、兆瓦充电，户储的高压/低压系统、混合逆变器、认证等。

---

# 13. 指标与“销量排名”处理规则

## 13.1 Observation 设计

任何数值数据保存为 Observation：

```text
observation_id
metric_id
entity_id
value
unit
currency
period_start
period_end
region
source_id
document_id
methodology
source_grade
is_estimate
confidence
```

## 13.2 指标可比性检查

只有满足以下条件才可以排序：

- 同一指标定义；
- 相近统计周期；
- 相近地域范围；
- 相同或可转换单位；
- 样本来源具有可比性；
- 明确知道“销量”“出货量”“装机量”“运营量”等口径差异。

## 13.3 排名规则

系统输出排名分为三类：

### R1：公开事实排名

来源提供完整或明确榜单，可直接复现。

### R2：可比数据重算排名

各企业数据来自可靠来源且统计口径一致，由系统排序。

### R3：竞争活动度排名

当没有真实销量数据时，只能基于事件、订单、项目、渠道等构建“市场活动度指数”，必须明确标注为分析性指标，不得称为“销量排名”。

## 13.4 禁止规则

如果只有零散新闻，禁止输出：

> “本周销量第一是 A 公司。”

可以输出：

> “在本周可观测公开信息中，A 公司项目与渠道活动度最高；该结论不等同于销量排名。”

---

# 14. 数据库 Schema（V1）

建议 SQLite 表：

## 14.1 `topics`

保存 Topic 版本、名称、状态。

## 14.2 `entities`

```text
entity_id
entity_type
canonical_name
country
metadata_json
created_at
updated_at
```

## 14.3 `entity_aliases`

```text
alias
entity_id
language
source
```

## 14.4 `sources`

```text
source_id
source_name
source_type
trust_grade
base_domain
status
```

## 14.5 `documents`

保存标准化文档元数据与正文索引。

## 14.6 `events`

```text
event_id
topic_id
event_type
title
event_date
summary
impact_score
confidence_score
primary_entity_id
status
```

## 14.7 `event_documents`

Event 与 supporting document 多对多关系。

## 14.8 `observations`

保存价格、销量、出货、项目金额等量化数据。

## 14.9 `claims`

保存分析报告中的关键事实/判断：

```text
claim_id
claim_text
claim_type          # fact / inference / forecast
confidence
report_id
```

## 14.10 `claim_evidence`

```text
claim_id
document_id
observation_id
evidence_role
```

## 14.11 `runs`

保存每次运行：

```text
run_id
task_id
topic_id
started_at
finished_at
status
documents_found
events_created
errors_count
llm_cost_estimate
```

## 14.12 `reports`

记录报告路径、周期、摘要、生成版本。

## 14.13 `notifications`

记录微信推送是否成功、重试次数等。

---

# 15. 证据、可信度与事实审计体系

## 15.1 Claim 类型

每条重要结论必须标记：

- `FACT`：来源直接支持；
- `INFERENCE`：系统基于多条事实进行判断；
- `FORECAST`：预测；
- `UNKNOWN`：证据不足。

## 15.2 Source Score

建议内部 0–100 评分，仅作为算法权重：

```text
来源权威性              0–30
是否为一手资料           0–25
是否有交叉验证           0–20
数据定义是否清晰         0–15
时间相关性              0–10
```

评分权重必须可配置，不作为对外“官方评级”。

## 15.3 Claim Confidence

综合：

- 来源等级；
- 支持来源数量；
- 是否一手；
- 不同来源是否一致；
- 数据口径一致性；
- 时间是否匹配；
- 是否包含可验证数字。

建议输出：

```text
High / Medium / Low
```

并保留数值分数供内部排序。

## 15.4 证据审计规则

关键结论必须满足：

```text
Claim
 ├─ evidence ≥ 1
 ├─ source identifiable
 ├─ source date available or marked unknown
 ├─ fact/inference explicitly separated
 └─ numeric claim has unit + period + scope
```

---

# 16. Agent 分工

V1 不需要真正运行很多独立服务，但逻辑上应拆成多个 Agent/Stage。

## 16.1 Search Planner Agent

输入：Topic + Task。  
输出：结构化查询计划。

## 16.2 Extraction Agent

输入：单篇文档。  
输出：

- 实体；
- 事件；
- 日期；
- 关键数字；
- 单位；
- 地区；
- 原文证据片段位置；
- 是否存在不确定性。

## 16.3 Event Consolidation Agent

判断多篇文章是否属于同一事件，并生成事件摘要。

## 16.4 Competitor Analyst

针对企业：

- 本周期动态；
- 与过去周期比较；
- 竞争动作；
- 可能战略意图；
- 证据强弱；
- 风险和机会。

## 16.5 Market Analyst

分析：

- 市场规模变化；
- 排名；
- 地区差异；
- 渠道；
- 价格；
- 需求；
- 政策。

## 16.6 Technology Analyst

分析：

- 新产品；
- 技术路线；
- 参数升级；
- 技术热度；
- 商业化进展。

## 16.7 Risk Signal Agent

识别：

- 事故；
- 召回；
- 诉讼；
- 合规；
- 供应链异常；
- 财务恶化；
- 重大负面舆情。

## 16.8 Review Agent

这是必须有的一层。检查：

- 报告中的数字是否存在于结构化数据；
- 日期是否错位；
- 是否把估算说成事实；
- 是否把活动度说成销量；
- 是否存在无证据结论；
- 是否存在互相矛盾的数据；
- 结论与证据强度是否匹配。

---

# 17. LLM 调用策略

## 17.1 Provider 抽象

系统不绑定单一模型，统一接口：

```python
class LLMProvider:
    def generate(self, messages, schema=None, temperature=0): ...
```

配置层决定具体供应商和模型。

## 17.2 模型分层

### 轻量模型

用于：

- 分类；
- 字段抽取；
- 标签；
- 简短摘要；
- 去重辅助。

### 强模型

用于：

- 多源综合；
- 竞争格局；
- 趋势推理；
- 复杂矛盾处理；
- 最终报告。

## 17.3 结构化输出

模型抽取结果必须要求 JSON Schema 或等价严格结构，避免自由文本难以入库。

## 17.4 Prompt 版本化

每次 Prompt 修改记录版本：

```text
prompt_id
version
changed_at
reason
```

Report 中记录使用的 prompt/model 版本，保证以后可以解释为什么同类数据产生不同分析。

---

# 18. 竞争情报分析指标

以下指标都是**内部分析指数**，不等于官方统计。

## 18.1 Competitive Activity Index（竞争活动度）

考虑：

- 重大项目；
- 中标；
- 产品发布；
- 合作；
- 渠道；
- 扩产；
- 海外扩张。

## 18.2 Market Momentum Index（市场动量）

考虑：

- 真实出货/销量变化（若有）；
- 新订单；
- 项目进展；
- 渠道扩张；
- 多周期趋势。

## 18.3 Technology Heat Index（技术热度）

考虑技术词出现、产品发布、专利/研发、项目落地等。

## 18.4 Risk Signal Index（风险信号）

考虑：

- 负面事件数量；
- 来源等级；
- 事故严重程度；
- 诉讼/监管；
- 财务异常；
- 多源确认。

## 18.5 Evidence Coverage（证据覆盖率）

```text
有证据支撑的关键 Claim 数 / 全部关键 Claim 数
```

这是系统内部最重要的质量指标之一。

---

# 19. 历史比较机制

每次分析至少比较：

- 当前周期；
- 上一周期；
- 过去 4 周均值；
- 过去 12 周趋势；
- 过去 52 周（有足够数据后）。

可构建：

```text
事件速度 Event Velocity
品牌公开活动 Share of Voice
重大项目增长率
技术词热度变化
价格变化
渠道变化
负面风险变化
```

历史比较必须考虑“本周新闻变多”不等于“市场真实销量变多”。

---

# 20. 报告体系

## 20.1 微信摘要

控制为手机可快速阅读的结构：

```text
【产业竞争情报周报 | 主题 | 周期】

一、本周一句话判断
……

二、最重要的 5 件事
1. ……
2. ……

三、企业竞争变化
- A：……
- B：……

四、关键数据
- ……

五、风险/机会
- ……

六、需要继续跟踪
- ……

数据质量：High/Medium
完整报告：仓库报告路径
```

## 20.2 Markdown 完整报告

建议结构：

1. 执行摘要；
2. 本周期核心结论；
3. 市场关键数据；
4. 竞争格局；
5. 重点企业动态；
6. 产品与技术；
7. 价格与渠道；
8. 政策与监管；
9. 投融资/并购/项目；
10. 风险信号；
11. 机会判断；
12. 历史趋势比较；
13. 下周期重点监测清单；
14. 数据完整性说明；
15. 来源与证据附录。

## 20.3 Excel 输出

至少包含 Sheet：

- `Run_Summary`
- `Events`
- `Companies`
- `Metrics`
- `Documents`
- `Claims`
- `Evidence`
- `Data_Quality`

## 20.4 报告中的结论标签

建议采用：

```text
[事实]
[推断]
[预测]
[数据不足]
```

避免读者把所有文字都理解为事实。

---

# 21. 微信推送设计

## 21.1 V1 通道

```text
Report Engine
   ↓
Notification Adapter
   ↓
Server酱 HTTP API
   ↓
微信
```

## 21.2 推送类型

### 正常周报

发送精简摘要。

### 重大事件即时提醒（V2）

只有达到阈值的高影响事件才推送，避免骚扰。

### 运行失败告警

例如：

```text
【情报Agent运行失败】
任务：charging_cn_weekly
阶段：Data Governance
原因：……
run_id：……
```

## 21.3 推送失败

- 自动重试；
- 保存 notification 状态；
- 推送失败不回滚已生成报告；
- 下次运行提示上次通知失败。

## 21.4 通道可替换

通知层使用 Adapter，未来可替换：

- 企业微信；
- 飞书；
- 钉钉；
- Email；
- Telegram；
- Slack。

核心系统无需修改。

---

# 22. 状态管理与增量运行

系统不能每次都重新抓取互联网历史全部数据。

## 22.1 State 文件

每个 Topic 保存：

```text
last_successful_run
last_search_window
known_document_hashes
known_event_ids
source_health
prompt_version
schema_version
```

## 22.2 增量策略

默认：

```text
本次开始时间 = 上次成功运行时间 - overlap buffer
```

建议回看 24–48 小时，防止网站延迟发布或搜索引擎延迟收录。

## 22.3 幂等性

同一任务重复运行不能产生大量重复 Event、Observation 或 Report Record。

---

# 23. 错误处理机制

## 23.1 错误分级

### P0：系统级致命错误

如配置无法读取、数据库损坏。

### P1：关键功能错误

如 LLM 全部失败、报告无法生成。

### P2：数据源错误

单一或部分来源不可访问。

### P3：数据质量警告

如来源时间缺失、指标口径不清。

## 23.2 Partial Success

例如 20 个来源有 3 个失败：

系统仍然完成报告，但明确写：

```text
本期数据完整性：Medium
失败来源：3
可能影响：招投标数据覆盖不足
```

不要因为一个源失败就让整条流水线失效。

---

# 24. 日志与可观测性

每次运行生成：

```text
run_id
stage
start_time
end_time
status
input_count
output_count
error_count
warning_count
cost
```

建议阶段日志：

```text
01_config
02_planning
03_collection
04_parsing
05_dedup
06_extraction
07_metrics
08_analysis
09_review
10_reporting
11_notification
12_persist
```

日志中不得打印 Secret。

---

# 25. 数据质量指标

每期报告附系统质量信息：

```text
文档有效率
去重率
高等级来源占比
关键 Claim 证据覆盖率
数值口径完整率
时间字段完整率
来源失败率
模型结构化输出成功率
```

推荐 V1 验收目标：

- 关键 Claim 证据覆盖率：100%；
- 无来源量化事实：0 条；
- 事实/推断标签遗漏：0 个关键结论；
- Topic 切换需要修改核心 Python：0 次；
- 单一来源失败导致全任务失败：0 次；
- 敏感 Key 写入仓库：0 次。

---

# 26. 安全设计

## 26.1 Repository

首期建议使用私有仓库。

## 26.2 Secret

所有密钥使用 GitHub Actions Secrets。

## 26.3 最小权限

Workflow 仅获得完成任务所需权限。例如只有需要提交数据时才授予 `contents: write`。

## 26.4 第三方 Action

尽量使用 GitHub 官方或高可信 Action；关键生产流程可以固定版本/commit，避免第三方 Action 被替换后引入供应链风险。

## 26.5 数据泄漏

送给 LLM 的数据要经过字段筛选。未来若加入企业内部数据，应增加 `data_classification`，禁止敏感数据发送到未经批准的模型接口。

---

# 27. 成本控制

成本来源：

1. GitHub Actions 运行时间；
2. 搜索/API；
3. LLM token；
4. 未来商业数据源；
5. 未来云服务器。

## 27.1 LLM 成本策略

```text
规则/正则可以做 → 不调用 LLM
轻量抽取 → 轻量模型
多源综合 → 强模型
全文太长 → 先本地切片/筛选
重复文档 → 不重复调用模型
```

## 27.2 缓存

保存：

- document hash；
- extraction result；
- event cluster；
- query fingerprint。

同一内容不重复付费分析。

---

# 28. 测试体系

## 28.1 Unit Test

覆盖：

- 配置加载；
- URL 标准化；
- hash；
- 时间解析；
- 单位转换；
- Topic override；
- source grading；
- SQLite schema。

## 28.2 Integration Test

覆盖完整小样本：

```text
Topic → Search Plan → Mock Documents → Event → Analysis → Report
```

## 28.3 Golden Dataset

准备约 30–50 条人工确认资料作为标准样本，验证：

- 企业识别；
- 事件分类；
- 数字抽取；
- 去重；
- Claim–Evidence 关系。

## 28.4 Golden Report

保存一份人工认可的报告结构，每次升级 Prompt 后对比结构和关键字段。

---

# 29. 首个 Topic：充电桩试验方案

## 29.1 试验目的

不是为了把充电桩行业一次研究到最深，而是验证整套基础设施是否成立。

## 29.2 V1 关注内容

- 重点企业/品牌重大事件；
- 产品和技术；
- 项目/中标/合作；
- 运营数据；
- 政策；
- 充电量/站/桩等公开指标；
- 价格/服务费等可获取信息；
- V2G、超充、液冷等技术进展；
- 公开排名及其口径；
- 风险事件。

## 29.3 首期输出

每周：

- 微信摘要；
- 1 份完整 Markdown；
- 1 份 Excel；
- 结构化 Events/Metrics；
- 数据质量报告。

---

# 30. 第二 Topic：户储迁移验证

户储不是另起炉灶，而是**系统通用性的验收测试**。

验收问题：

1. 是否仅新增 `home_storage.yaml` 就能运行？
2. 主程序是否需要修改行业关键词？必须不需要。
3. 是否能使用原有 Source Adapter？
4. 是否能自动形成不同指标和报告重点？
5. 是否能正常识别“出货量/渠道/库存/价格”等户储特有指标？
6. 如果某特殊行业数据源无法覆盖，是否只新增 Adapter，而非修改核心流程？

如果上述测试通过，才能认定“通用产业情报 Agent”架构成立。

---

# 31. 开发实施阶段

## Phase 0：项目骨架与规范

### 工作内容

- 创建 GitHub 私有仓库；
- 建目录；
- 建配置模板；
- 建数据 Schema；
- 建日志规范；
- 建 Secrets/Variables 清单；
- 建 CI 校验。

### 验收

`python main.py --validate` 能验证所有配置和目录。

---

## Phase 1：最小可用采集链路

### 工作内容

- Topic Loader；
- Task Loader；
- Search Planner；
- 基础 Search/HTML/RSS Adapter；
- 文档标准化；
- hash 去重；
- JSONL 持久化。

### 验收

对充电桩主题能采集到过去 7 天的结构化文档，重复数据可识别。

---

## Phase 2：事件与指标抽取

### 工作内容

- 实体别名；
- 事件分类；
- Observation；
- Event 聚类；
- LLM 结构化抽取；
- SQLite 建库。

### 验收

随机抽查 30 条资料，关键企业、事件、数字、单位、时间基本正确，并可追溯到原文。

---

## Phase 3：竞争情报分析

### 工作内容

- 企业周度比较；
- 行业趋势；
- 技术分析；
- 风险分析；
- 内部指数；
- 历史比较。

### 验收

分析结果中的关键 Claim 全部能链接证据。

---

## Phase 4：Review 与报告

### 工作内容

- Review Agent；
- Markdown 周报；
- Excel；
- 微信摘要；
- 数据质量章节。

### 验收

不得出现“无来源数字”“活动度冒充销量”等错误。

---

## Phase 5：GitHub 全自动运行

### 工作内容

- scheduled dispatcher；
- manual workflow；
- Secrets；
- 自动提交数据；
- Artifact；
- 失败通知；
- retry。

### 验收

在无本地电脑参与情况下完成一次全流程并收到微信报告。

---

## Phase 6：户储主题迁移验证

### 工作内容

- 新增 Topic；
- 不改核心代码；
- 运行 30 天户储情报任务；
- 记录需要新增的特殊数据源插件。

### 验收

核心 Python 不因行业切换而修改。

---

## Phase 7：稳定性与成本优化

### 工作内容

- 缓存；
- 并发；
- 模型分层；
- source health；
- 数据压缩；
- 失败恢复；
- 运行统计。

---

# 32. 迁移到云服务器的触发条件

GitHub V1 足够时继续使用；出现以下情况则建议迁移：

1. 大量国内站点对 GitHub IP 不稳定；
2. Playwright 任务显著增多；
3. 单次运行时间明显增长；
4. 数据规模不适合持续提交 Git；
5. 需要 PostgreSQL/对象存储；
6. 需要小时级甚至更高频监控；
7. 需要稳定 IP、代理、VPN 或企业网络；
8. 需要企业内部数据；
9. 需要多用户权限管理；
10. 需要长期高可靠生产运行。

迁移后的目标架构可变为：

```text
GitHub（代码/CI）
        ↓
云服务器 / Docker
        ↓
PostgreSQL + Object Storage
        ↓
Scheduler
        ↓
同一套 Python Core
```

Topic、Task、Prompt、Schema 不变。

---

# 33. V1 关键技术决策清单

- **应用形态**：无网站、无 APP。
- **运行环境**：GitHub Actions。
- **语言**：Python 3.12 左右的稳定版本。
- **配置**：YAML。
- **持久事实数据**：JSONL/CSV，必要时 Parquet。
- **查询层**：SQLite，可重建。
- **浏览器自动化**：Playwright，仅必要时使用。
- **分析**：可切换 LLM Provider。
- **报告**：Markdown + Excel + 微信摘要。
- **微信**：Server酱 Adapter。
- **安全**：GitHub Secrets。
- **测试**：pytest + fixtures + golden data。
- **CI**：config/schema/unit tests。
- **部署迁移**：Docker-ready，但 V1 不强制 Docker。

---

# 34. 开发时的“禁止硬编码”清单

以下内容不得直接散落在核心 Python：

- 行业名；
- 企业名；
- 关键词；
- 地区；
- 关注指标；
- 报告栏目；
- 来源等级；
- LLM 模型名；
- 推送 Token；
- 时间周期；
- 排名定义；
- 技术词；
- 事件词。

必须来源于：配置、Schema、环境变量或 Adapter。

---

# 35. 最终验收标准

系统 V1 被认定成功，至少满足：

## 功能

- [ ] 能定时运行；
- [ ] 能手动运行；
- [ ] 能选择 Topic；
- [ ] 能覆盖地区/企业/时间/关注维度；
- [ ] 能采集多来源；
- [ ] 能去重；
- [ ] 能生成 Event；
- [ ] 能抽取指标；
- [ ] 能保存历史；
- [ ] 能分析历史变化；
- [ ] 能生成 Markdown；
- [ ] 能生成 Excel；
- [ ] 能推送微信；
- [ ] 能失败告警。

## 通用性

- [ ] 从充电桩切换至户储，不修改核心业务代码；
- [ ] 新 Topic 通过 YAML 加入；
- [ ] 新特殊网站通过 Adapter 加入；
- [ ] LLM 可以替换供应商；
- [ ] 通知渠道可替换。

## 数据可信度

- [ ] 关键事实均有证据；
- [ ] 数字有单位、周期、地区/口径；
- [ ] 推断不会写成事实；
- [ ] 无真实数据时不会伪造销量排名；
- [ ] 报告有数据完整性说明；
- [ ] 来源等级可追踪。

## 安全

- [ ] Secrets 不进入 Git；
- [ ] 日志不输出 Secrets；
- [ ] 私有仓库；
- [ ] 不绕过访问控制；
- [ ] Workflow 使用最小权限。

---

# 36. 第一轮实际开发建议顺序

后续进入实操时，严格建议按以下顺序执行，而不是一开始写大量爬虫：

```text
01 创建仓库
02 建目录
03 定 Schema
04 定 Topic / Task 配置格式
05 写配置校验器
06 写数据存储层
07 写最基础 Search/HTML Adapter
08 做充电桩 20–50 条小样本
09 做去重 / Event / Observation
10 做证据链
11 做 LLM 抽取
12 做 Review
13 做周报模板
14 接微信
15 接 GitHub schedule/manual
16 连续跑几次
17 新增户储 Topic
18 验证不改主程序
19 再扩充特殊 Source Adapter
20 最后做性能与成本优化
```

这是本项目最重要的开发纪律之一。

---

# 37. 建议的第一版任务配置

## Task 01：充电桩周报

```yaml
id: charging_cn_weekly
topic_id: charging_pile
window: 7d
regions: [China]
report_depth: standard
notify: true
```

目标：跑通全链路。

## Task 02：户储迁移测试

```yaml
id: home_storage_validation
topic_id: home_storage
window: 30d
regions: [China, Germany, Italy]
report_depth: deep
notify: false
```

目标：验证通用架构。

---

# 38. 后续高级能力路线

V2/V3 可以逐步增加：

- 自然语言生成 Task Config；
- 重大事件条件触发提醒；
- 产业链关系图；
- 企业竞争画像；
- 价格曲线；
- 自动图表；
- RAG 历史问答；
- 多 Topic 联动分析；
- “某公司过去半年战略变化”自动追溯；
- 事件异常检测；
- 预测与情景分析；
- 数据源健康评分；
- 企业内部数据融合；
- 研究员人工审核入口；
- 企业微信/飞书等多通道；
- 云数据库与对象存储。

这些能力都建立在 V1 的 Topic/Task/Claim/Evidence/Data Schema 之上，因此 V1 的数据结构设计非常关键。

---

# 39. 技术实现依据与当前约束（核验于 2026-08-11）

本规划对 GitHub 首期能力的判断依据 GitHub 官方文档进行核验：

1. GitHub Actions 支持 `schedule` 定时触发 workflow；官方提示高负载时可能延迟，整点为典型高负载时间，因此本规划采用类似 08:17 的非整点调度。
2. Scheduled workflow 默认使用 UTC，但当前官方文档也支持通过 IANA timezone 指定时区；实现时仍应在应用层统一保存标准时区并测试。
3. `workflow_dispatch` 支持从 GitHub UI、CLI 或 REST API 手动运行，并可接收输入；本规划用它实现临时 Topic/时间/地区/企业覆盖。
4. GitHub Actions Secrets 用于敏感凭据；Variables 用于非敏感配置。
5. GitHub Actions Artifacts 可以保存运行文件并设置保留期，因此适合运行产物和调试文件，但本规划不将其作为唯一长期数据存储。
6. Server酱当前提供通过 HTTP API 向微信等通道推送消息的能力，适合作为 V1 的通知 Adapter；未来通知层保持可替换。

> 具体 API 参数、额度、GitHub Action 版本、模型 API 字段等属于可能变化的实现细节。进入开发阶段时，应再次以官方最新文档核验，不在核心架构中写死。

---

# 40. 项目结论

本项目应被定义为：

> **一个以 Topic Profile + Task Config 为业务入口，以多源采集和可追溯证据链为数据基础，以 LLM 为分析增强而非事实来源，以 GitHub Actions 为首期执行环境，以微信为轻量通知终端的通用产业竞争情报自动化 Agent。**

首期成功的真正标准不是“充电桩周报生成了”，而是：

> **完成充电桩后，只新增户储 Topic 和必要配置，就能在不改核心业务代码的情况下自动完成另一行业的采集、治理、分析和推送。**

一旦这一点被验证，后续增加工商业储能、逆变器、固态电池、机器人、汽车零部件或其他行业，都属于“扩展 Topic/Source”，而不是重新开发一套系统。

---

## 附录 A：后续正式开发时第一批需要创建的文件

```text
README.md
pyproject.toml
main.py
config/system.yaml
config/schedules.yaml
config/topics/_template.yaml
config/topics/charging_pile.yaml
config/topics/home_storage.yaml
config/tasks/_template.yaml
config/tasks/charging_cn_weekly.yaml
config/sources/search.yaml
config/taxonomies/event_types.yaml
config/taxonomies/source_grades.yaml
config/taxonomies/metrics.yaml
src/controller/config_loader.py
src/controller/task_controller.py
src/planner/search_planner.py
src/storage/jsonl_store.py
src/storage/sqlite_store.py
src/governance/deduplicator.py
src/governance/evidence.py
src/entities/resolver.py
src/analysis/base.py
src/reporting/markdown_report.py
src/notification/serverchan.py
scripts/validate_config.py
scripts/rebuild_db.py
tests/unit/
.github/workflows/validation.yml
.github/workflows/manual_run.yml
.github/workflows/scheduled_dispatcher.yml
```

## 附录 B：后续操作优先级

**最高优先级：** Schema、配置、证据链、可重建数据层。  
**第二优先级：** 充电桩小样本采集与事件抽取。  
**第三优先级：** 周报、微信、GitHub 自动化。  
**第四优先级：** 户储迁移验证。  
**第五优先级：** 扩展更多数据源和高级分析。

