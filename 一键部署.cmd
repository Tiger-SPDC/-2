@echo off
setlocal

set "DEPLOY_PS=powershell.exe"
where pwsh.exe >nul 2>&1 && set "DEPLOY_PS=pwsh.exe"

"%DEPLOY_PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\04_One-Click-Deploy.ps1" %*
set "DEPLOY_EXIT=%ERRORLEVEL%"

echo.
if "%DEPLOY_EXIT%"=="0" (
  echo Deployment command finished successfully.
) else (
  echo Deployment failed with exit code %DEPLOY_EXIT%.
)
echo You may close this window after reviewing the result.
pause >nul
exit /b %DEPLOY_EXIT%
