# 数据库、证据链、历史比较与状态管理

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
