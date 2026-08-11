# 数据源、采集、标准化、去重、实体、事件与指标

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
