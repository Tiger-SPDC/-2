# 试验 Topic、实施阶段、迁云、硬编码约束与验收

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
