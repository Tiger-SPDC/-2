[CmdletBinding()]
param(
    [string]$Repository = "",
    [ValidateSet("private", "public")]
    [string]$Visibility = "private",
    [ValidatePattern("^[A-Za-z0-9_-]+$")]
    [string]$TaskId = "charging_cn_weekly",
    [switch]$LocalOnly,
    [switch]$SkipTests,
    [switch]$SkipFirstRun,
    [switch]$WaitForFirstRun,
    [switch]$NonInteractive,
    [switch]$InstallPrerequisites
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OriginalLocation = (Get-Location).Path
$script:GhCommand = $null

function Write-Step {
    param([int]$Number, [int]$Total, [string]$Message)
    Write-Host ""
    Write-Host "[$Number/$Total] $Message" -ForegroundColor Cyan
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments | Out-Host
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed ($exitCode): $FilePath $($Arguments -join ' ')"
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Confirm-PrerequisiteInstall {
    param([string]$DisplayName)

    if ($InstallPrerequisites) {
        return $true
    }
    if ($NonInteractive) {
        return $false
    }

    $answer = Read-Host "$DisplayName is missing. Install it with winget now? [Y/n]"
    return [string]::IsNullOrWhiteSpace($answer) -or $answer.Trim().ToLowerInvariant() -eq "y"
}

function Install-WingetPackage {
    param([string]$PackageId, [string]$DisplayName)

    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "$DisplayName is required and winget is unavailable. Install $DisplayName, then rerun."
    }
    if (-not (Confirm-PrerequisiteInstall $DisplayName)) {
        throw "$DisplayName is required. Installation was not approved."
    }

    Write-Host "Installing $DisplayName with winget..." -ForegroundColor Yellow
    Invoke-External "winget.exe" install --id $PackageId --exact --source winget `
        --accept-package-agreements --accept-source-agreements
    Refresh-ProcessPath
}

function Get-UsablePythonCandidates {
    $candidates = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = "py.exe"; Prefix = @("-3.12") }
        $candidates += [pscustomobject]@{ Exe = "py.exe"; Prefix = @("-3.11") }
    }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = (Get-Command python.exe).Source; Prefix = @() }
    }
    if (Get-Command python3.exe -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = (Get-Command python3.exe).Source; Prefix = @() }
    }
    return $candidates
}

function Test-PythonCandidate {
    param([object]$Candidate)

    $exe = [string]$Candidate.Exe
    $prefix = @($Candidate.Prefix)
    $probe = @"
import os, sys
ok = sys.version_info >= (3, 11) and os.path.isfile(sys.executable)
raise SystemExit(0 if ok else 1)
"@
    try {
        & $exe @prefix -c $probe *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function New-IsolatedEnvironment {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        & $venvPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw "The existing .venv does not use Python 3.11+. Remove it manually and rerun."
        }
        Write-Host "[OK] Reusing project .venv." -ForegroundColor Green
        return $venvPython
    }

    $candidates = @(Get-UsablePythonCandidates)
    $usable = $null
    foreach ($candidate in $candidates) {
        if (Test-PythonCandidate $candidate) {
            $usable = $candidate
            break
        }
    }

    if ($null -eq $usable) {
        Install-WingetPackage "Python.Python.3.12" "Python 3.12"
        $candidates = @(Get-UsablePythonCandidates)
        foreach ($candidate in $candidates) {
            if (Test-PythonCandidate $candidate) {
                $usable = $candidate
                break
            }
        }
    }
    if ($null -eq $usable) {
        throw "Python 3.11+ was not found after prerequisite setup."
    }

    $exe = [string]$usable.Exe
    $prefix = @($usable.Prefix)
    Write-Host "Creating the isolated .venv..."
    & $exe @prefix -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Python could not create the project .venv."
    }
    Write-Host "[OK] Created project .venv." -ForegroundColor Green
    return $venvPython
}

function Get-GitHubCli {
    $installed = Get-Command gh.exe -ErrorAction SilentlyContinue
    if ($installed) {
        return $installed.Source
    }

    $portableRoot = Join-Path $ProjectRoot ".tools\gh"
    $portable = Get-ChildItem -LiteralPath $portableRoot -Filter gh.exe -Recurse `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($portable) {
        return $portable.FullName
    }

    Write-Host "Downloading the official portable GitHub CLI..." -ForegroundColor Yellow
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $architecture = if ($env:PROCESSOR_ARCHITEW6432 -eq "ARM64" -or `
        $env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/cli/cli/releases/latest" `
        -Headers @{ "User-Agent" = "industry-intelligence-agent-deployer" }
    $assetPattern = "_windows_$architecture.zip$"
    $asset = $release.assets | Where-Object { $_.name -match $assetPattern } | Select-Object -First 1
    if (-not $asset) {
        throw "No compatible GitHub CLI release asset was found for $architecture."
    }

    New-Item -ItemType Directory -Path $portableRoot -Force | Out-Null
    $archive = Join-Path $portableRoot $asset.name
    $downloadParameters = @{
        Uri = $asset.browser_download_url
        OutFile = $archive
        Headers = @{ "User-Agent" = "industry-intelligence-agent-deployer" }
    }
    if ($PSVersionTable.PSVersion.Major -lt 6) {
        $downloadParameters.UseBasicParsing = $true
    }
    Invoke-WebRequest @downloadParameters
    Expand-Archive -LiteralPath $archive -DestinationPath $portableRoot -Force
    $portable = Get-ChildItem -LiteralPath $portableRoot -Filter gh.exe -Recurse | Select-Object -First 1
    if (-not $portable) {
        throw "GitHub CLI was downloaded but gh.exe was not found."
    }
    Write-Host "[OK] Portable GitHub CLI is ready." -ForegroundColor Green
    return $portable.FullName
}

function Test-TcpAddress {
    param([string]$Address, [int]$Port = 443, [int]$TimeoutMilliseconds = 3000)

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($Address, $Port)
        if (-not $task.Wait($TimeoutMilliseconds)) {
            return $false
        }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Resolve-ReachableGitHubWebAddress {
    $providers = @(
        "https://cloudflare-dns.com/dns-query?name=github.com&type=A",
        "https://dns.google/resolve?name=github.com&type=A"
    )
    $addresses = @()
    foreach ($provider in $providers) {
        try {
            $response = Invoke-RestMethod -Uri $provider -Headers @{ Accept = "application/dns-json" } `
                -TimeoutSec 15
            $addresses += @($response.Answer | Where-Object { $_.type -eq 1 } `
                | ForEach-Object { $_.data })
        } catch {
            Write-Host "[WARN] DNS-over-HTTPS provider was unavailable: $provider" `
                -ForegroundColor Yellow
        }
    }
    foreach ($address in @($addresses | Select-Object -Unique)) {
        if (Test-TcpAddress $address) {
            return $address
        }
    }
    throw "No reachable HTTPS address for github.com was found."
}

function Invoke-GitHubLoginRequest {
    param([string]$Address, [string]$Endpoint, [hashtable]$Form)

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) {
        throw "curl.exe is required for the GitHub login network fallback."
    }
    $arguments = @(
        "--silent",
        "--show-error",
        "--fail-with-body",
        "--resolve", "github.com:443:$Address",
        "--request", "POST",
        "--header", "Accept: application/json"
    )
    foreach ($key in $Form.Keys) {
        $arguments += @("--data-urlencode", "$key=$($Form[$key])")
    }
    $arguments += "https://github.com$Endpoint"

    $responseText = & $curl.Source @arguments
    $requestExitCode = $LASTEXITCODE
    if ($requestExitCode -ne 0) {
        throw "GitHub login request failed ($requestExitCode)."
    }
    try {
        return $responseText | ConvertFrom-Json
    } catch {
        throw "GitHub login returned an invalid response."
    }
}

function Invoke-GitHubDeviceLoginFallback {
    # Public OAuth client id embedded in the official GitHub CLI binary.
    $clientId = "178c6fc778ccc68e1d6a"
    $address = Resolve-ReachableGitHubWebAddress
    Write-Host "Using a process-local GitHub network fallback ($address)." -ForegroundColor Yellow

    $device = Invoke-GitHubLoginRequest $address "/login/device/code" @{
        client_id = $clientId
        scope = "repo read:org gist workflow"
    }
    if (-not $device.device_code -or -not $device.user_code) {
        throw "GitHub did not return a device authorization code."
    }

    Write-Host "GitHub one-time code: $($device.user_code)" -ForegroundColor Cyan
    Write-Host "Opening $($device.verification_uri)"
    Start-Process $device.verification_uri

    $interval = [Math]::Max(5, [int]$device.interval)
    $deadline = [DateTime]::UtcNow.AddSeconds([int]$device.expires_in)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds $interval
        $tokenResponse = Invoke-GitHubLoginRequest $address "/login/oauth/access_token" @{
            client_id = $clientId
            device_code = [string]$device.device_code
            grant_type = "urn:ietf:params:oauth:grant-type:device_code"
        }
        if ($tokenResponse.access_token) {
            $accessToken = [string]$tokenResponse.access_token
            try {
                $accessToken | & $script:GhCommand auth login --hostname github.com `
                    --git-protocol https --with-token | Out-Host
                $tokenExitCode = $LASTEXITCODE
                if ($tokenExitCode -ne 0) {
                    throw "GitHub CLI could not store the authorized token."
                }
            } finally {
                $accessToken = $null
            }
            Write-Host "[OK] GitHub device authorization completed." -ForegroundColor Green
            return
        }

        switch ([string]$tokenResponse.error) {
            "authorization_pending" { continue }
            "slow_down" { $interval += 5; continue }
            "access_denied" { throw "GitHub device authorization was denied." }
            "expired_token" { throw "GitHub device authorization expired." }
            default {
                $description = [string]$tokenResponse.error_description
                throw "GitHub device authorization failed: $description"
            }
        }
    }
    throw "GitHub device authorization expired before completion."
}

function Ensure-GitHubAuthentication {
    # gh uses a non-zero exit code to report an expected "not logged in" state.
    # Temporarily relax native-command error handling so that state can be handled here.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $script:GhCommand auth status --hostname github.com *> $null
        $statusExitCode = $LASTEXITCODE
        if ($statusExitCode -eq 0) {
            Write-Host "[OK] GitHub authentication is active." -ForegroundColor Green
        } else {
            if ($NonInteractive) {
                throw "GitHub authentication is required. Run 'gh auth login' first or set GH_TOKEN."
            }
            Write-Host "A browser authorization is required once for your GitHub account." -ForegroundColor Yellow
            & $script:GhCommand auth login --hostname github.com --git-protocol https --web
            $loginExitCode = $LASTEXITCODE
            if ($loginExitCode -ne 0) {
                Write-Host "[WARN] Standard GitHub login failed; trying the network fallback." `
                    -ForegroundColor Yellow
                Invoke-GitHubDeviceLoginFallback
            }
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    Invoke-External $script:GhCommand auth setup-git
}

function Get-GitHubLogin {
    $login = & $script:GhCommand api user --jq .login
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($login)) {
        throw "Unable to read the authenticated GitHub account."
    }
    return $login.Trim()
}

function Initialize-LocalRepository {
    param([string]$Login)

    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        Install-WingetPackage "Git.Git" "Git for Windows"
    }
    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        throw "Git was not found after prerequisite setup."
    }

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git"))) {
        & git.exe init --initial-branch=main | Out-Host
        $initExitCode = $LASTEXITCODE
        if ($initExitCode -ne 0) {
            Invoke-External "git.exe" init
            Invoke-External "git.exe" branch --move --force main
        }
    }

    $gitName = & git.exe config --get user.name
    if ([string]::IsNullOrWhiteSpace($gitName)) {
        Invoke-External "git.exe" config user.name $Login
    }
    $gitEmail = & git.exe config --get user.email
    if ([string]::IsNullOrWhiteSpace($gitEmail)) {
        Invoke-External "git.exe" config user.email "$Login@users.noreply.github.com"
    }

    Invoke-External "git.exe" add --all
    $secretMatches = & git.exe grep --cached -n -I -E `
        "(sk-[A-Za-z0-9_-]{20,}|SCT[A-Za-z0-9_-]{20,})" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host $secretMatches -ForegroundColor Red
        throw "A likely API key was found in files selected for commit. Remove it before deployment."
    }
    if ($LASTEXITCODE -gt 1) {
        throw "The pre-push secret scan failed."
    }

    & git.exe diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Invoke-External "git.exe" commit --message "chore: enable one-click automated deployment"
    } else {
        Write-Host "[OK] No uncommitted project changes." -ForegroundColor Green
    }

    $branch = & git.exe branch --show-current
    if ([string]::IsNullOrWhiteSpace($branch)) {
        Invoke-External "git.exe" branch --move --force main
        $branch = "main"
    }
    return $branch.Trim()
}

function Test-RepositoryName {
    param([string]$Name)
    return $Name -match "^(?:[A-Za-z0-9][A-Za-z0-9._-]*)(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?$"
}

function Resolve-RemoteRepository {
    param([string]$Login, [string]$Branch)

    $originUrl = & git.exe remote get-url origin 2>$null
    $hasOrigin = $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($originUrl)

    if ($hasOrigin) {
        $infoRaw = & $script:GhCommand repo view --json nameWithOwner,viewerPermission,url
        if ($LASTEXITCODE -ne 0) {
            throw "The existing origin cannot be accessed with the authenticated GitHub account: $originUrl"
        }
        $info = $infoRaw | ConvertFrom-Json
        if ($Repository -and $Repository -ne $info.nameWithOwner -and `
            $Repository -ne ($info.nameWithOwner -split "/")[-1]) {
            throw "-Repository does not match the existing origin ($($info.nameWithOwner))."
        }
        if ($info.viewerPermission -notin @("ADMIN", "MAINTAIN", "WRITE")) {
            throw "The authenticated account does not have write access to $($info.nameWithOwner)."
        }
        Invoke-External "git.exe" push --set-upstream origin $Branch
        return $info.nameWithOwner
    }

    $target = $Repository
    if ([string]::IsNullOrWhiteSpace($target)) {
        $defaultTarget = "$Login/industry-intelligence-agent"
        if ($NonInteractive) {
            $target = $defaultTarget
        } else {
            $answer = Read-Host "GitHub repository [$defaultTarget]"
            $target = if ([string]::IsNullOrWhiteSpace($answer)) { $defaultTarget } else { $answer.Trim() }
        }
    }
    if (-not (Test-RepositoryName $target)) {
        throw "Invalid repository name: $target"
    }
    if ($target -notmatch "/") {
        $target = "$Login/$target"
    }

    & $script:GhCommand repo view $target --json nameWithOwner,viewerPermission *> $null
    if ($LASTEXITCODE -eq 0) {
        $existingRaw = & $script:GhCommand repo view $target --json nameWithOwner,viewerPermission
        $existing = $existingRaw | ConvertFrom-Json
        if ($existing.viewerPermission -notin @("ADMIN", "MAINTAIN", "WRITE")) {
            throw "Repository $target exists but the authenticated account cannot write to it."
        }
        Invoke-External "git.exe" remote add origin "https://github.com/$target.git"
        Invoke-External "git.exe" push --set-upstream origin $Branch
        return $existing.nameWithOwner
    }

    $visibilityFlag = "--$Visibility"
    Invoke-External $script:GhCommand repo create $target $visibilityFlag --source $ProjectRoot `
        --remote origin --push --description "Configurable industry intelligence automation agent"
    $created = & $script:GhCommand repo view --json nameWithOwner --jq .nameWithOwner
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($created)) {
        throw "Repository was created but its canonical name could not be read."
    }
    return $created.Trim()
}

function Set-RepositoryJsonSetting {
    param([string]$Endpoint, [hashtable]$Body, [string]$Description)

    $json = $Body | ConvertTo-Json -Compress
    $json | & $script:GhCommand api --method PUT $Endpoint --input - *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $Description" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not set $Description. An organization policy may control it." `
            -ForegroundColor Yellow
    }
}

function Test-RemoteSecret {
    param([string]$Repo, [string]$Name)
    $lines = & $script:GhCommand secret list --repo $Repo --app actions 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Name))\s") {
            return $true
        }
    }
    return $false
}

function Set-RemoteSecretValue {
    param([string]$Repo, [string]$Name, [string]$Value)
    $Value | & $script:GhCommand secret set $Name --repo $Repo --app actions | Out-Host
    $secretExitCode = $LASTEXITCODE
    if ($secretExitCode -ne 0) {
        throw "Failed to set GitHub Actions secret $Name."
    }
    Write-Host "[OK] Secret $Name is configured (value hidden)." -ForegroundColor Green
}

function Ensure-RemoteSecret {
    param(
        [string]$Repo,
        [string]$Name,
        [string]$Prompt,
        [bool]$Required
    )

    $environmentValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($environmentValue)) {
        Set-RemoteSecretValue $Repo $Name $environmentValue
        return $true
    }
    if (Test-RemoteSecret $Repo $Name) {
        Write-Host "[OK] Secret $Name already exists on GitHub." -ForegroundColor Green
        return $true
    }
    if ($NonInteractive) {
        $level = if ($Required) { "WARN" } else { "INFO" }
        Write-Host "[$level] Secret $Name was not provided; the related feature will degrade." `
            -ForegroundColor Yellow
        return $false
    }

    Write-Host "$Prompt (input is hidden; press Enter to skip)"
    $secure = Read-Host -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $plain = $null
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ([string]::IsNullOrWhiteSpace($plain)) {
            $level = if ($Required) { "WARN" } else { "INFO" }
            Write-Host "[$level] $Name was skipped; the related feature will degrade." `
                -ForegroundColor Yellow
            return $false
        }
        Set-RemoteSecretValue $Repo $Name $plain
        return $true
    } finally {
        $plain = $null
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Enable-AutomationWorkflows {
    param([string]$Repo)

    Set-RepositoryJsonSetting "repos/$Repo/actions/permissions" `
        @{ enabled = $true; allowed_actions = "all" } "GitHub Actions enabled"
    Set-RepositoryJsonSetting "repos/$Repo/actions/permissions/workflow" `
        @{ default_workflow_permissions = "write"; can_approve_pull_request_reviews = $false } `
        "workflow token write permission enabled"

    $workflows = @(
        "ci.yml",
        "manual_run.yml",
        "scheduled_dispatcher.yml",
        "validation.yml",
        "maintenance.yml"
    )
    foreach ($workflow in $workflows) {
        & $script:GhCommand workflow enable $workflow --repo $Repo *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] $workflow could not be explicitly enabled; it may already be active." `
                -ForegroundColor Yellow
        }
    }
    Write-Host "[OK] Automation workflows are available." -ForegroundColor Green
}

function Start-FirstWorkflowRun {
    param([string]$Repo, [string]$Branch, [bool]$Notify)

    $notifyValue = if ($Notify) { "true" } else { "false" }
    $triggerOutput = $null
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        $triggerOutput = & $script:GhCommand workflow run manual_run.yml --repo $Repo --ref $Branch `
            --raw-field "task_id=$TaskId" --raw-field "depth=standard" `
            --raw-field "notify=$notifyValue" --raw-field "force=true" 2>&1
        if ($LASTEXITCODE -eq 0) {
            break
        }
        if ($attempt -eq 6) {
            Write-Host $triggerOutput -ForegroundColor Red
            throw "The first Manual Run could not be triggered."
        }
        Start-Sleep -Seconds (2 * $attempt)
    }

    Write-Host "[OK] First Manual Run was queued." -ForegroundColor Green
    $runUrl = ($triggerOutput | Select-String -Pattern "https://github.com/.+/actions/runs/\d+" `
        | Select-Object -Last 1).Matches.Value

    if ($WaitForFirstRun) {
        Start-Sleep -Seconds 5
        $runRaw = & $script:GhCommand run list --repo $Repo --workflow manual_run.yml --limit 1 `
            --json databaseId,url,status,conclusion
        if ($LASTEXITCODE -ne 0) {
            throw "The queued workflow run could not be located."
        }
        $run = ($runRaw | ConvertFrom-Json | Select-Object -First 1)
        if (-not $run) {
            throw "The queued workflow run could not be located."
        }
        $runUrl = $run.url
        Invoke-External $script:GhCommand run watch ([string]$run.databaseId) --repo $Repo --exit-status
    }
    return $runUrl
}

try {
    Set-Location $ProjectRoot
    Write-Host "=== Industry Intelligence Agent: One-Click Deployment ===" -ForegroundColor Cyan
    Write-Host "Project root: $ProjectRoot"
    Write-Host "Secrets are never written to project files."

    Write-Step 1 7 "Create or reuse the isolated Python environment"
    $venvPython = New-IsolatedEnvironment

    Write-Step 2 7 "Install project dependencies"
    Invoke-External $venvPython -m pip install --upgrade pip
    Invoke-External $venvPython -m pip install --editable ".[dev]"

    Write-Step 3 7 "Validate configuration and code"
    Invoke-External $venvPython main.py --version
    Invoke-External $venvPython main.py --validate
    Invoke-External $venvPython scheduler.py --validate-schedules
    if (-not $SkipTests) {
        $testTemp = Join-Path $ProjectRoot ".tmp\pytest"
        New-Item -ItemType Directory -Path (Split-Path $testTemp -Parent) -Force | Out-Null
        $previousPytestAddopts = $env:PYTEST_ADDOPTS
        try {
            $env:PYTEST_ADDOPTS = "-p no:cacheprovider"
            Invoke-External $venvPython -m pytest --quiet --basetemp $testTemp
        } finally {
            if ($null -eq $previousPytestAddopts) {
                Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
            } else {
                $env:PYTEST_ADDOPTS = $previousPytestAddopts
            }
        }
        Invoke-External (Join-Path $ProjectRoot ".venv\Scripts\ruff.exe") check .
        Invoke-External (Join-Path $ProjectRoot ".venv\Scripts\mypy.exe") src
    }

    if ($LocalOnly) {
        Write-Step 4 7 "Local-only mode selected"
        Write-Host "[OK] Local deployment is ready." -ForegroundColor Green
        Write-Host "Run: .\.venv\Scripts\python.exe scheduler.py --dry-run"
        exit 0
    }

    Write-Step 4 7 "Prepare GitHub authentication"
    $script:GhCommand = Get-GitHubCli
    Ensure-GitHubAuthentication
    $login = Get-GitHubLogin

    Write-Step 5 7 "Initialize, scan, commit, and push the repository"
    $branch = Initialize-LocalRepository $login
    $repo = Resolve-RemoteRepository $login $branch
    Write-Host "[OK] Code is pushed to $repo." -ForegroundColor Green

    Write-Step 6 7 "Configure Actions and encrypted Secrets"
    Enable-AutomationWorkflows $repo
    $hasDeepSeek = Ensure-RemoteSecret $repo "DEEPSEEK_API_KEY" `
        "Enter your DeepSeek API key" $true
    $hasServerChan = Ensure-RemoteSecret $repo "SERVERCHAN_KEY" `
        "Enter your ServerChan SendKey" $false

    Write-Step 7 7 "Queue the first acceptance run"
    $runUrl = $null
    if ($SkipFirstRun) {
        Write-Host "[INFO] First Manual Run was skipped by request."
    } else {
        $runUrl = Start-FirstWorkflowRun $repo $branch $hasServerChan
    }

    $repoUrl = "https://github.com/$repo"
    Write-Host ""
    Write-Host "=== Deployment complete ===" -ForegroundColor Green
    Write-Host "Repository: $repoUrl"
    Write-Host "Actions:    $repoUrl/actions"
    if (-not [string]::IsNullOrWhiteSpace($runUrl)) {
        Write-Host "First run:  $runUrl"
    }
    if (-not $hasDeepSeek) {
        Write-Host "Note: LLM analysis is in degraded mode until DEEPSEEK_API_KEY is configured." `
            -ForegroundColor Yellow
    }
    if (-not $hasServerChan) {
        Write-Host "Note: WeChat notification is disabled until SERVERCHAN_KEY is configured." `
            -ForegroundColor Yellow
    }
} catch {
    Write-Host ""
    Write-Host "Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Fix the reported item and rerun; completed steps are safe to reuse." -ForegroundColor Yellow
    exit 1
} finally {
    Set-Location $OriginalLocation
}
