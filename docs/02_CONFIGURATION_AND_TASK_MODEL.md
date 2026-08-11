# 配置体系与检索规划

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
