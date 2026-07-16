param(
    [string]$TargetPath = "",
    [string]$RepoOwner = "BennyCryptoGuru",
    [string]$RepoName = "Automat",
    [string]$Branch = "main",
    [string]$ArchiveUrl = "",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$ScriptPath = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ([string]::IsNullOrWhiteSpace($TargetPath)) {
    $TargetPath = (Resolve-Path -LiteralPath (Join-Path $ScriptPath "..")).Path
}
$TargetPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetPath)
$UpdateLockPath = Join-Path $TargetPath "data\update.lock"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Set-UpdateLock {
    $lockDir = Split-Path -Parent $UpdateLockPath
    New-Item -ItemType Directory -Force -Path $lockDir | Out-Null
    Set-Content -LiteralPath $UpdateLockPath -Value (Get-Date -Format o) -Encoding UTF8
}

function Clear-UpdateLock {
    Remove-Item -LiteralPath $UpdateLockPath -Force -ErrorAction SilentlyContinue
}

function Remove-DirectoryInside([string]$Root, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $rootPath = (Resolve-Path -LiteralPath $Root).Path
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete a path outside the target folder: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Get-AutomatProcessIds {
    $ids = @()
    try {
        $ids += Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess
    } catch {
    }
    $escapedTarget = [regex]::Escape($TargetPath)
    $escapedRunPy = [regex]::Escape((Join-Path $TargetPath "run.py"))
    $ids += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.Name -match "python" -and (
                    $_.CommandLine -match $escapedRunPy -or
                    ($_.CommandLine -match "run\.py" -and $_.CommandLine -match $escapedTarget)
                )
            )
        } |
        Select-Object -ExpandProperty ProcessId
    return $ids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique
}

function Stop-AutomatIfRunning {
    $ids = @(Get-AutomatProcessIds)
    if (-not $ids.Count) {
        Write-Host "Automat is not running."
        return
    }
    foreach ($id in $ids) {
        try {
            Write-Host "Stopping running Automat PID $id"
            Stop-Process -Id $id -Force -ErrorAction Stop
        } catch {
            Write-Warning "Could not stop process PID $id with Stop-Process: $($_.Exception.Message)"
            & taskkill.exe /PID $id /F /T | Out-Null
        }
    }
    $deadline = (Get-Date).AddSeconds(12)
    do {
        Start-Sleep -Milliseconds 300
        $stillListening = @(Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue)
    } while ($stillListening.Count -and (Get-Date) -lt $deadline)
    if ($stillListening.Count) {
        throw "Port 5000 is still in use. Close Automat manually and run the update again."
    }
}

function Start-AutomatAfterUpdate {
    if ($NoRestart) {
        Write-Host "Restart skipped because -NoRestart was used."
        return
    }
    $launcher = Join-Path $TargetPath "start.bat"
    if (-not (Test-Path -LiteralPath $launcher)) {
        Write-Warning "Start launcher was not found: $launcher"
        return
    }
    Write-Step "Starting Automat"
    Write-Host "Automat will use visible mode unless Stealth run is enabled in settings."
    Start-Process -FilePath $launcher -WorkingDirectory $TargetPath
}

function Get-GitHubArchiveUrl {
    if (-not [string]::IsNullOrWhiteSpace($ArchiveUrl)) {
        return $ArchiveUrl
    }
    return "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
}

function Download-GitHubSource([string]$TemporaryRoot) {
    $url = Get-GitHubArchiveUrl
    $zipPath = Join-Path $TemporaryRoot "automat-source.zip"
    $extractPath = Join-Path $TemporaryRoot "source"

    Write-Step "Downloading Automat from GitHub"
    Write-Host "URL: $url"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

    Write-Step "Extracting downloaded source"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
    $source = Get-ChildItem -LiteralPath $extractPath -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "run.py")) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "automat"))
        } |
        Select-Object -First 1
    if (-not $source) {
        throw "The downloaded GitHub archive does not look like Automat source code."
    }
    return $source.FullName
}

function Copy-ProgramFiles([string]$SourcePath) {
    Write-Step "Copying program files"
    $excludedDirectories = @(
        ".git",
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "data",
        "zalohy",
        "production version",
        "produkcni verze"
    )
    $excludedFiles = @(
        ".env",
        ".env.*",
        "*.log",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.rar",
        "*.zip",
        "*.7z",
        "*.sqlite",
        "*.sqlite3"
    )

    Get-ChildItem -LiteralPath $SourcePath -Directory -Force |
        Where-Object { $excludedDirectories -notcontains $_.Name } |
        ForEach-Object {
            $target = Join-Path $TargetPath $_.Name
            & robocopy $_.FullName $target /MIR /XD "__pycache__" ".pytest_cache" /XF $excludedFiles /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -gt 7) { throw "Copying folder $($_.Name) failed (robocopy $LASTEXITCODE)." }
        }

    Get-ChildItem -LiteralPath $SourcePath -File -Force |
        Where-Object {
            $name = $_.Name
            -not ($excludedFiles | Where-Object { $name -like $_ })
        } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetPath $_.Name) -Force
        }
}

function Backup-LocalData {
    $dataPath = Join-Path $TargetPath "data"
    if (-not (Test-Path -LiteralPath $dataPath)) {
        return
    }
    $hasDatabase = Test-Path -LiteralPath (Join-Path $dataPath "automat.db")
    $hasScreenshots = @(Get-ChildItem -LiteralPath (Join-Path $dataPath "screenshots") -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne ".gitkeep" }).Count -gt 0
    if (-not $hasDatabase -and -not $hasScreenshots) {
        return
    }

    Write-Step "Backing up local data"
    $backupRoot = Join-Path $dataPath "backups"
    $backupPath = Join-Path $backupRoot ("update-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path $backupPath | Out-Null
    & robocopy $dataPath $backupPath /E /XD "backups" /XF "*.log" /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Backing up local data failed (robocopy $LASTEXITCODE)." }
    Write-Host "Backup created: $backupPath"
}

function Remove-ObsoleteProgramFiles {
    Write-Step "Removing obsolete program folders"
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "production version")
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "produkcni verze")

    $obsoleteRootFiles = @(
        "add_watchdog_to_startup.ps1",
        "disable_stealth_run.ps1",
        "install.ps1",
        "start_hidden.ps1",
        "start_hidden.vbs",
        "update.ps1",
        "watchdog.py",
        "watchdog_hidden.ps1",
        "watchdog_hidden.vbs"
    )
    foreach ($file in $obsoleteRootFiles) {
        $path = Join-Path $TargetPath $file
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

Write-Host "Automat - GitHub update" -ForegroundColor Magenta
Write-Host "Target: $TargetPath"
Write-Host "Repository: $RepoOwner/$RepoName"
Write-Host "Branch: $Branch"
Write-Host "Local data in data and the .venv environment will be preserved."

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
$temporaryRoot = Join-Path $env:TEMP ("Automat-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null

try {
    Set-UpdateLock

    Write-Step "Stopping running Automat"
    Stop-AutomatIfRunning

    Backup-LocalData

    $downloadedSource = Download-GitHubSource $temporaryRoot
    Copy-ProgramFiles $downloadedSource

    Remove-ObsoleteProgramFiles

    Write-Step "Cleaning old temporary files"
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "__pycache__")
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath ".pytest_cache")

    Write-Step "Checking dependencies"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $TargetPath "scripts\install.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation or update failed." }

    Write-Host "`nUpdate from GitHub is complete." -ForegroundColor Green
    Write-Host "The database, screenshots, logs, and browser-independent local data in data were preserved."
    Start-AutomatAfterUpdate
} finally {
    Clear-UpdateLock
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
