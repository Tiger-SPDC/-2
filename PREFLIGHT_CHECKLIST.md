# PREFLIGHT_CHECKLIST

## A. 本机基础环境

- [ ] Windows 10 1809+ / Windows 11
- [ ] Git 可用：`git --version`
- [ ] Python 3.11+ 可用：`python --version` 或 `py -0p`
- [ ] Claude Code 可用：`claude --version`
- [ ] 项目目录是独立目录，不是其他项目的子目录
- [ ] 没有为本项目设置系统级 ANTHROPIC_* 环境变量

## B. 项目隔离

- [ ] `.venv` 位于项目根目录
- [ ] `.gitignore` 已存在
- [ ] `CLAUDE.md` 已存在
- [ ] 不使用已有 Conda 环境
- [ ] 不使用用户 Chrome/Edge Profile

## C. 账号/密钥

- [ ] 已有 DeepSeek API Key
- [ ] Key 未写入仓库
- [ ] Key 未写入 `.env.example`
- [ ] GitHub 账号可用
- [ ] （可后置）Private GitHub 仓库已创建

## D. 当前明确不做

- [ ] 不安装数据库服务
- [ ] 不配置 Windows 计划任务
- [ ] 不配置微信推送
- [ ] 不运行真实爬虫
- [ ] 不让 Claude 自主跨 Phase

## E. 进入 Phase 0 前需要回传给 ChatGPT

只需要告诉 ChatGPT：

1. `00_Check-Environment.ps1` 的结果；
2. 项目实际路径；
3. `.venv` 是否创建成功；
4. `claude --version` 是否正常；
5. DeepSeek API Key 是否已经准备好（只回答“是/否”，不要发送 Key）。
