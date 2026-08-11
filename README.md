# Industry Intelligence Agent

通用产业竞争情报自动化 Agent。

## 1. 项目名称

Industry Intelligence Agent（industry-intelligence-agent）。

## 2. 项目目标

构建一套无网站、低人工干预、可配置、可追溯、可扩展的产业竞争情报自动化系统。

通过 `Topic Profile + Task Config` 双层配置切换行业、企业、地区、时间范围与关注指标，核心代码不绑定具体行业。首个验证主题为中国充电基础设施，第二验证主题为户用储能。

## 3. 当前阶段

- **阶段：** Phase 0 — 项目骨架与规范（本阶段完成工程骨架、环境隔离、基础测试与 CI）。
- **业务代码：** 尚未开始。
- 更多规划见 `docs/00_MASTER_PLAN.md` 与 `ROADMAP.md`。

## 4. 核心设计原则

- 核心代码行业无关：行业知识通过 `config/topics/*.yaml` 配置。
- 数据源可插拔：新数据源通过 Source Adapter 扩展。
- LLM 通过 Provider 抽象调用，不绑定单一厂商或模型。
- 通知通过 Notifier 抽象，渠道可替换。
- 事实与推断分离：`FACT` / `INFERENCE` / `FORECAST` 必须区分。
- 证据优先：关键结论必须回链到可追溯来源。

## 5. 目录结构

```text
├── .github/workflows/       GitHub Actions（当前仅 CI）
├── config/                  配置（system/topics/tasks/sources/prompts）
├── src/industry_intelligence/  核心 Python 包
├── tests/                   unit / integration / fixtures
├── data/                    raw / normalized / intelligence / state / cache
├── reports/                 报告输出
├── logs/                    日志
├── scripts/                 PowerShell 环境脚本
├── docs/                    架构文档与 Phase 指令
├── pyproject.toml
├── main.py                  基础入口
└── README.md
```

## 6. Python 环境要求

- Python >= 3.11（优先 3.12；本机如无 3.12，可用 3.11）。

## 7. `.venv` 使用方法

项目内创建隔离虚拟环境（禁止全局安装）：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

或运行：

```powershell
.\scripts\01_Create-Isolated-Venv.ps1
```

## 8. 开发依赖安装方式

只安装到 `.venv`：

```powershell
.\.venv\Scripts\pip install -e ".[dev]"
```

开发依赖仅包括：`pytest`、`pytest-cov`、`ruff`、`mypy`。

## 9. 测试命令

```powershell
.\.venv\Scripts\python main.py
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\mypy src
```

## 10. 当前禁止事项

Phase 0 阶段禁止实现：真实爬虫、搜索/新闻/RSS 抓取、SQLite 业务模型、Topic/Task/Source/Evidence Schema、LLM API、Server酱/企业微信、Markdown/Excel 周报、GitHub cron、历史比较、竞争指数、事件聚类、实体识别。

禁止操作：修改项目目录外文件、全局 pip 安装、修改 Windows PATH/注册表/系统环境变量、创建计划任务/系统服务、复用日常浏览器 Profile、在仓库中写入任何 API Key/Token。

## 11. Roadmap

- 阶段总览：`ROADMAP.md`
- 系统总设计：`docs/00_MASTER_PLAN.md`
- 当前阶段指令：`docs/phase_instructions/PHASE_0_BOOTSTRAP.md`
- 项目宪法与安全边界：`CLAUDE.md`、`SECURITY_BOUNDARY.md`
