$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Host "Project boundary: $ProjectRoot" -ForegroundColor Cyan
Write-Host "The Claude project must remain inside this directory." -ForegroundColor Yellow

$required = @("CLAUDE.md", "ROADMAP.md", "docs", ".gitignore")
$ok = $true
foreach ($r in $required) {
    if (Test-Path (Join-Path $ProjectRoot $r)) {
        Write-Host "[OK] $r" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Missing $r" -ForegroundColor Red
        $ok = $false
    }
}
if (-not $ok) { exit 1 }
Write-Host "Boundary package looks complete." -ForegroundColor Green
