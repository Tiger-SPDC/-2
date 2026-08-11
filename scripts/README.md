# scripts 使用顺序

1. `00_Check-Environment.ps1`：只读检查，不修改系统。
2. `01_Create-Isolated-Venv.ps1`：只在项目目录创建 `.venv`。
3. `03_Verify-Project-Boundary.ps1`：检查项目约束文件是否齐全。
4. `02_Start-Claude-DeepSeek-Flash.ps1`：等 ChatGPT 发出正式 Phase 0 指令时使用。

如果 PowerShell 因执行策略阻止脚本，不要修改系统级执行策略。可以仅对当前进程临时允许：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

关闭该 PowerShell 后设置即失效。
