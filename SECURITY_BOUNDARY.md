# SECURITY_BOUNDARY

## 本机边界

本项目只能在项目根目录及其子目录工作。任何父目录、兄弟目录、用户 Home 下其他项目均属于禁止区域。

## Secret 边界

任何真实密钥只能存在于：

- 启动脚本当前进程的临时环境变量；或
- 后续 GitHub Actions repository secrets。

不得进入 Git 历史。

## 网络边界

Phase 0 不需要访问业务数据源。后续采集只访问公开且允许自动访问的资源，不绕过验证码、登录限制、付费墙、机器人限制或技术访问控制。

## 浏览器边界

任何 Playwright/Chromium 自动化必须使用独立 Profile/CI 临时 Profile，不复用用户日常浏览器数据。

## 破坏性命令

默认禁止：

- `git reset --hard`
- `git clean -fdx`
- 递归删除项目外路径
- 全局包卸载/升级
- 系统级环境变量修改
- 注册表修改
- Windows 服务/计划任务创建
