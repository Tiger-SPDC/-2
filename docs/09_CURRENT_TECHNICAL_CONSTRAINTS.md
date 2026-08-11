# 当前技术依据与总体结论

本文件由 V1.0 总设计说明书拆分而成，用于 Claude Code 按需读取，避免每次加载完整长文档。

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
