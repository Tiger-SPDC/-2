$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "Creating isolated Python environment in: $ProjectRoot\.venv" -ForegroundColor Cyan

if (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "[OK] .venv already exists. No change made." -ForegroundColor Green
    & ".venv\Scripts\python.exe" --version
    exit 0
}

$created = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -eq 0) { $created = $true }
}
if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -m venv .venv
    if ($LASTEXITCODE -eq 0) { $created = $true }
}
if (-not $created) {
    throw "Unable to create .venv. Install Python 3.11+ (3.12 recommended) and retry."
}

Write-Host "[OK] Isolated environment created." -ForegroundColor Green
& ".venv\Scripts\python.exe" --version
Write-Host "No global Python packages were modified." -ForegroundColor Green
Write-Host "Do not install business dependencies until Phase 0 instructions are issued." -ForegroundColor Yellow
