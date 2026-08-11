# 先看我：Claude + DeepSeek V4 Flash 开发前准备

本包的目的不是立即开始写业务代码，而是把本项目放进一个**不会干扰你电脑其他项目**的安全工作区。

## 推荐最终路径

建议将整个文件夹放到一个独立、英文路径中，例如：

```text
D:\AI_Projects\industry-intelligence-agent
```

不要把项目放在：

- `D:\` 根目录；
- 你的 MAPF、论文、数学建模、电力市场等已有项目目录中；
- OneDrive/网盘自动同步且会频繁改文件的目录；
- 已有 Python/Conda 项目的子目录中。

## 你现在只需要完成 5 件事

1. 把本包解压/复制到独立项目目录。
2. 打开 PowerShell，进入项目目录。
3. 运行 `scripts\00_Check-Environment.ps1`（只检查，不改系统）。
4. 如果 Python 检查通过，运行 `scripts\01_Create-Isolated-Venv.ps1` 创建项目独立 `.venv`。
5. 确认你已拥有 DeepSeek API Key；**不要把 Key 写进任何项目文件，也不要发到聊天中**。

完成后，不要先让 Claude 写代码。下一阶段由用户把环境检查结果告诉 ChatGPT，再生成正式 Phase 0 指令。

## Claude Code 推荐安装方式（Windows）

优先使用 Anthropic 当前推荐的 Native Install，而不是为了 Claude Code 额外污染 npm 全局环境。

PowerShell：

```powershell
irm https://claude.ai/install.ps1 | iex
claude --version
```

Git for Windows 建议安装，因为 Claude Code 在原生 Windows 上可以借助它使用 Bash 工具；如果没有，也可以使用 PowerShell shell。

## DeepSeek 接入原则

本项目**不设置 Windows 系统级/用户级 ANTHROPIC 环境变量**。

使用：

```text
scripts\02_Start-Claude-DeepSeek-Flash.ps1
```

脚本会：

1. 只在当前进程设置 DeepSeek Anthropic API 地址与 V4 Flash 模型；
2. 提示你临时输入 API Key；
3. 在当前项目目录启动 `claude`；
4. Claude 退出后清理本次进程中的相关变量。

因此不会把 DeepSeek 配置永久写到其他 Claude 项目。

## 现在不要准备的东西

当前阶段不需要：

- Docker / WSL2；
- MySQL / PostgreSQL；
- Server酱 SendKey；
- 搜索 API Key；
- Playwright 浏览器；
- 大量 Python 包；
- Windows 计划任务；
- 任何爬虫账号或 Cookie。

这些只在对应 Phase 需要时再配置。

## GitHub

可以现在创建，也可以 Phase 0 后创建。建议：

- 仓库名：`industry-intelligence-agent`
- 可见性：Private
- 如果现在创建空仓库，先不要自动添加 README / .gitignore / License，避免和本地骨架冲突。
- API Key/Token 后续只放 GitHub Actions Secrets。

## 开始 Claude 前的硬规则

始终从项目目录启动 Claude；不要在 `D:\`、用户 Home 或你的科研总目录启动。

进入 Claude 后，第一条正式开发指令将由 ChatGPT 下一阶段提供。不要先发送“帮我把整个项目做完”。
