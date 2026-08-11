# GitHub Actions、安全、成本与测试

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
