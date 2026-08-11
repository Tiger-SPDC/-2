$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw "Claude Code is not installed or not in PATH. Run 'claude --version' first."
}

Write-Host "=== Claude Code + DeepSeek V4 Flash (project-isolated session) ===" -ForegroundColor Cyan
Write-Host "Working directory: $ProjectRoot"
Write-Host "No Windows User/Machine environment variables will be written." -ForegroundColor Green
Write-Host ""

$apiKeyPlain = $env:DEEPSEEK_API_KEY
if (-not $apiKeyPlain) {
    $secure = Read-Host "Enter DeepSeek API Key (input hidden; not saved)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $apiKeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
if (-not $apiKeyPlain) { throw "No API key provided." }

$vars = @(
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
)

try {
    $env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
    $env:ANTHROPIC_AUTH_TOKEN = $apiKeyPlain
    $env:ANTHROPIC_MODEL = "deepseek-v4-flash"
    $env:ANTHROPIC_DEFAULT_OPUS_MODEL = "deepseek-v4-flash"
    $env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-flash"
    $env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "deepseek-v4-flash"
    $env:CLAUDE_CODE_SUBAGENT_MODEL = "deepseek-v4-flash"
    $env:CLAUDE_CODE_EFFORT_LEVEL = "max"
    $env:CLAUDE_CODE_AUTO_COMPACT_WINDOW = "786432"

    Write-Host "[OK] Temporary DeepSeek V4 Flash environment configured." -ForegroundColor Green
    Write-Host "[OK] Starting Claude only inside this project." -ForegroundColor Green
    Write-Host ""
    & claude
}
finally {
    foreach ($v in $vars) { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
    $apiKeyPlain = $null
    Remove-Variable secure -ErrorAction SilentlyContinue
    Write-Host "Temporary DeepSeek/Anthropic session variables cleared." -ForegroundColor Green
}
