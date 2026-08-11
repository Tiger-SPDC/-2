# Phase 0 — 项目工程骨架与基础设施初始化

> 项目：通用产业竞争情报自动化 Agent（Industry Intelligence Agent）  
> 当前阶段：Phase 0  
> 本阶段目标：只完成工程骨架、环境隔离、基础测试与 CI。  
> **禁止提前进入 Phase 1 及之后阶段。**

---

## 1. 执行前必须阅读

开始修改任何文件前，依次阅读：

1. `CLAUDE.md`
2. `SECURITY_BOUNDARY.md`
3. `ROADMAP.md`
4. `PROJECT_STATUS.md`
5. `DECISIONS.md`
6. `docs/00_MASTER_PLAN.md`
7. `docs/01_PROJECT_VISION_AND_ARCHITECTURE.md`

如文件缺失，不要猜测内容，记录缺失项后继续完成能够确定的 Phase 0 工作。

---

## 2. 最高级安全约束

### 2.1 文件系统
只允许访问和修改**当前 Git 仓库内部**。

禁止：

- 修改父目录或兄弟目录；
- 扫描或修改其他科研/算法项目；
- 删除仓库外任何文件；
- 将项目文件写到仓库外；
- 修改其他 Git 仓库。

### 2.2 Python 环境
必须使用项目自己的：

```text
.venv
```

禁止：

```text
全局 pip install
pip install --user
修改 Conda base
修改其他 Conda 环境
```

### 2.3 Windows 系统
禁止：

- 修改 PATH；
- 修改注册表；
- 修改系统级/用户级永久环境变量；
- 修改 PowerShell Profile；
- 修改全局 Git 配置；
- 创建 Windows 计划任务；
- 安装后台系统服务。

### 2.4 浏览器
本阶段禁止安装或使用：

```text
Playwright
Selenium
ChromeDriver
```

---

## 3. 项目架构硬性原则

### 3.1 Core 不得绑定行业
`src/` 中禁止写死：

- 充电桩；
- 户储；
- 储能；
- 逆变器；
- 固态电池；
- 具体品牌或公司。

未来行业差异必须通过 `Topic Profile` 配置实现。

### 3.2 Source 可插拔
未来新数据源必须通过 `Source Adapter` 扩展。

禁止在主程序中不断增加：

```python
if website == ...
```

### 3.3 LLM 可替换
项目不得绑定 DeepSeek。

未来应支持统一 `LLMProvider` 抽象，可替换：

- DeepSeek
- OpenAI
- Anthropic
- Gemini
- 其他兼容模型

Phase 0 不实现具体 LLM API。

### 3.4 Notification 可替换
未来应支持 Server酱、企业微信、邮件等通知渠道。

Phase 0 不实现。

### 3.5 事实可信度
未来必须区分：

```text
FACT
INFERENCE
FORECAST
```

并建立：

```text
Claim
→ Evidence
→ Document
→ Source
```

证据链。

Phase 0 只保留这一架构要求，不实现业务逻辑。

---

# 4. Phase 0 具体任务

## Task 0.1 — 项目现状审计

先检查并记录：

- 当前目录结构；
- 现有文件；
- 是否存在 `.venv`；
- 是否是 Git 仓库；
- 是否存在 `pyproject.toml`；
- 是否存在测试框架；
- 是否存在未提交修改。

不得覆盖已有规划文档。

---

## Task 0.2 — 初始化标准目录

整理为：

```text
industry-intelligence-agent/
│
├── .github/
│   └── workflows/
│
├── config/
│   ├── system/
│   ├── topics/
│   ├── tasks/
│   ├── sources/
│   └── prompts/
│
├── src/
│   └── industry_intelligence/
│       ├── __init__.py
│       ├── core/
│       ├── config/
│       ├── collectors/
│       ├── sources/
│       ├── normalization/
│       ├── intelligence/
│       ├── llm/
│       ├── storage/
│       ├── reporting/
│       ├── notification/
│       └── utils/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── intelligence/
│   ├── state/
│   └── cache/
│
├── reports/
├── logs/
├── scripts/
├── docs/
│   └── phase_instructions/
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── ROADMAP.md
├── PROJECT_STATUS.md
├── DECISIONS.md
├── CLAUDE.md
└── main.py
```

已有目录不要重复创建。

---

## Task 0.3 — Python Package

创建：

```text
src/industry_intelligence/
```

Phase 0 只建立包结构和必要的 `__init__.py`。

禁止实现真实：

- 爬虫；
- 数据库；
- LLM；
- 报告；
- 通知；
- Topic Schema；
- Task Schema；
- Source Schema。

---

## Task 0.4 — `pyproject.toml`

要求：

```text
Python >= 3.11
```

Phase 0 仅允许引入必要开发依赖：

```text
pytest
pytest-cov
ruff
mypy
```

暂时不要安装：

```text
pandas
numpy
playwright
selenium
beautifulsoup4
openai
anthropic
sqlalchemy
fastapi
streamlit
```

合理配置：

- pytest；
- ruff；
- mypy；
- coverage。

不要过度工程化。

---

## Task 0.5 — `main.py`

当前只作为基础入口。

运行：

```bash
python main.py
```

应输出类似：

```text
Industry Intelligence Agent
Project bootstrap initialized.
Current phase: Phase 0
```

不要实现任何真实业务。

---

## Task 0.6 — 版本模块

创建：

```text
src/industry_intelligence/version.py
```

例如：

```python
__version__ = "0.1.0"
```

---

## Task 0.7 — `.gitignore`

至少忽略：

```text
.venv/
.env
.env.*
!.env.example

__pycache__/
*.py[cod]

.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

logs/*
!logs/.gitkeep

data/cache/*
!data/cache/.gitkeep

*.sqlite
*.sqlite3

.DS_Store
Thumbs.db

.idea/
.vscode/
```

不要误删 `data/raw`、`data/normalized`、`data/intelligence` 等目录。

---

## Task 0.8 — `.env.example`

只保留变量名，禁止写真实密钥：

```text
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

SEARCH_API_KEY=

SERVERCHAN_SENDKEY=

LOG_LEVEL=
```

---

## Task 0.9 — README

`README.md` 至少说明：

1. 项目名称；
2. 项目目标；
3. 当前阶段；
4. 核心设计原则；
5. 目录结构；
6. Python 环境要求；
7. `.venv` 使用方法；
8. 开发依赖安装方式；
9. 测试命令；
10. 当前禁止事项；
11. Roadmap 文件位置。

不要复制完整总设计文档。

---

## Task 0.10 — 基础测试

创建：

```text
tests/unit/test_bootstrap.py
```

至少验证：

- `industry_intelligence` 可 import；
- 版本号存在；
- `main.py` 基础入口可运行。

不要为了数量增加无意义测试。

---

## Task 0.11 — GitHub Actions CI

只创建：

```text
.github/workflows/ci.yml
```

仅用于：

```text
push / pull_request
→ Python 3.11
→ 安装开发依赖
→ ruff
→ mypy
→ pytest
```

禁止：

- `schedule`；
- cron；
- 网络爬虫；
- LLM API；
- 微信推送；
- GitHub 自动提交数据；
- Secrets 读取。

---

## Task 0.12 — 状态记录

更新：

```text
PROJECT_STATUS.md
CHANGELOG.md
```

版本：

```text
v0.1.0
Project bootstrap
```

保留已有内容，只追加或更新当前状态。

---

# 5. 本阶段明确禁止事项

本次不要实现：

```text
真实爬虫
搜索 API
新闻 API
RSS 抓取
Playwright / Selenium
SQLite 业务模型
JSONL 数据模型
Topic Schema
Task Schema
Source Schema
Evidence Schema
DeepSeek / OpenAI / Anthropic API
Server酱
企业微信
Markdown 周报
Excel 周报
GitHub cron
历史比较
竞争指数
销量分析
事件聚类
实体识别
自然语言任务解析
```

不要引入：

```text
FastAPI
Django
Flask
Streamlit
React
Vue
Redis
Celery
Kafka
Docker
Kubernetes
```

当前架构保持：

```text
Python Package
+
CLI
+
GitHub Actions CI
```

---

# 6. Git 操作规则

开始前先检查：

```bash
git status
```

如尚未初始化，可：

```bash
git init
```

禁止：

```text
git push
自行创建 GitHub 仓库
写入 GitHub Token
修改 global git config
```

如发现用户已有未提交修改，不得覆盖。

Phase 0 完成后可以运行：

```bash
git diff
git status --short
```

但不要自行执行最终 commit。

---

# 7. 测试与验收

完成后必须实际运行：

```bash
python main.py
pytest
ruff check .
mypy src
```

如果工具未安装，只能安装到当前 `.venv`。

禁止伪造成功结果。

---

# 8. Phase 0 验收标准

全部满足：

## 环境

- 未修改项目目录外文件；
- 未全局安装 Python 包；
- 未修改 Windows PATH；
- 未修改系统永久环境变量。

## 工程

- `src/industry_intelligence/` 存在；
- `tests/` 存在；
- `config/` 存在；
- `data/` 存在；
- `.github/workflows/ci.yml` 存在。

## Python

- `python main.py` 成功；
- 包可 import；
- 版本号可读取。

## Quality

- pytest 通过；
- ruff 通过；
- mypy 通过，或真实记录未解决问题。

## 安全

- 没有真实 API Key；
- `.env` 被忽略；
- `.env.example` 无真实凭证。

## 架构

- Core 不含行业硬编码；
- 没有提前实现 Phase 1+；
- 没有网站或前端系统。

---

# 9. 完成后的报告格式

完成后只按以下格式汇报：

```markdown
# Phase 0 Execution Report

## 1. Status
PASS / PARTIAL / FAIL

## 2. Files Created
...

## 3. Files Modified
...

## 4. Environment Changes
Project-local changes:
System-level changes: None

## 5. Tests
python main.py:
pytest:
ruff:
mypy:

## 6. Git Status
...

## 7. Architecture Compliance
Core industry-independent: YES/NO
No secrets committed: YES/NO
No global Python install: YES/NO
No external directories modified: YES/NO
No Phase 1+ implementation: YES/NO

## 8. Issues
None / ...

## 9. Decisions Needed From User
None / ...

## 10. STOP
Phase 0 completed.
Waiting for user review.
Phase 1 has NOT been started.
```

---

# 10. 决策优先级

如有冲突：

```text
CLAUDE.md
>
SECURITY_BOUNDARY.md
>
本 Phase 指令
>
docs 架构文件
>
ROADMAP.md
>
你自己的工程判断
```

如项目文档之间存在实质冲突，记录：

```text
ARCHITECTURE CONFLICT
```

不要自行重构整个系统。

---

# 11. 最终要求

你的目标不是一次性完成整个产业竞争情报系统。

本次唯一目标：

> **把 Phase 0 做干净、稳定、可验证，然后立即停止。**

完成 Phase 0 后，禁止自行进入 Phase 1。
