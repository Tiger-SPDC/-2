$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== Industry Intelligence Agent: Preflight Check ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "No system changes will be made."
Write-Host ""

function Test-Command($name, $args) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "[FAIL] $name not found" -ForegroundColor Red
        return $false
    }
    try {
        $output = & $name @args 2>&1 | Select-Object -First 1
        Write-Host "[OK]   $name -> $output" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[WARN] $name exists but version check failed: $_" -ForegroundColor Yellow
        return $false
    }
}

$gitOk = Test-Command "git" @("--version")
$claudeOk = Test-Command "claude" @("--version")

$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        $v = & py -3.12 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK]   Python -> $v (via py -3.12)" -ForegroundColor Green
            $pythonCmd = "py -3.12"
        }
    } catch {}
}
if (-not $pythonCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $v = & python --version 2>&1
    Write-Host "[INFO] Python -> $v" -ForegroundColor Cyan
    $pythonCmd = "python"
}
if (-not $pythonCmd) {
    Write-Host "[FAIL] Python 3.11+ not detected" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- Persistent ANTHROPIC_* environment variables ---" -ForegroundColor Cyan
$names = @(
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
)
$foundPersistent = $false
foreach ($n in $names) {
    $u = [Environment]::GetEnvironmentVariable($n, "User")
    $m = [Environment]::GetEnvironmentVariable($n, "Machine")
    if ($u -or $m) {
        $foundPersistent = $true
        Write-Host "[WARN] Persistent variable found: $n (User/Machine). Value not displayed." -ForegroundColor Yellow
    }
}
if (-not $foundPersistent) {
    Write-Host "[OK]   No persistent project-related ANTHROPIC_* variables detected." -ForegroundColor Green
}

Write-Host ""
Write-Host "--- Project boundary ---" -ForegroundColor Cyan
if (Test-Path (Join-Path $ProjectRoot "CLAUDE.md")) {
    Write-Host "[OK]   CLAUDE.md present" -ForegroundColor Green
} else {
    Write-Host "[FAIL] CLAUDE.md missing" -ForegroundColor Red
}
if (Test-Path (Join-Path $ProjectRoot ".gitignore")) {
    Write-Host "[OK]   .gitignore present" -ForegroundColor Green
}

$root = [System.IO.Path]::GetPathRoot($ProjectRoot).TrimEnd('\')
if ($ProjectRoot.TrimEnd('\') -eq $root) {
    Write-Host "[FAIL] Project appears to be at drive root. Move it to a dedicated subfolder." -ForegroundColor Red
} else {
    Write-Host "[OK]   Project is not at drive root" -ForegroundColor Green
}

Write-Host ""
Write-Host "--- Local virtual environment ---" -ForegroundColor Cyan
if (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe")) {
    $venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $vv = & $venvPy --version 2>&1
    Write-Host "[OK]   .venv exists -> $vv" -ForegroundColor Green
} else {
    Write-Host "[INFO] .venv not created yet. Run scripts\01_Create-Isolated-Venv.ps1" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Result ===" -ForegroundColor Cyan
Write-Host "If Git, Python, Claude, project boundary and persistent-env checks are OK, the machine is ready for Phase 0." 
Write-Host "Do NOT paste your DeepSeek API key into chat or any tracked file." -ForegroundColor Yellow
