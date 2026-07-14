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
    $TargetPath = $ScriptPath
}
$TargetPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetPath)

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
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
    $ids += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match $escapedTarget -or
                $_.CommandLine -match "AutomatBrowserStudio" -or
                ($_.CommandLine -match "run\.py" -and $_.Name -match "python")
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

function Start-AutomatHidden {
    if ($NoRestart) {
        Write-Host "Restart skipped because -NoRestart was used."
        return
    }
    $launcher = Join-Path $TargetPath "start_hidden.vbs"
    if (-not (Test-Path -LiteralPath $launcher)) {
        Write-Warning "Hidden launcher was not found: $launcher"
        return
    }
    Write-Step "Starting Automat hidden"
    Start-Process -FilePath "wscript.exe" -ArgumentList @("`"$launcher`"") -WorkingDirectory $TargetPath -WindowStyle Hidden
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
    $itemsToCopy = @(
        "automat",
        "tests",
        "install.bat",
        "install.ps1",
        "disable_stealth_run.bat",
        "disable_stealth_run.ps1",
        "update.bat",
        "update.ps1",
        "requirements.txt",
        "run.py",
        "watchdog.py",
        "watchdog_hidden.ps1",
        "watchdog_hidden.vbs",
        "add_watchdog_to_startup.bat",
        "add_watchdog_to_startup.ps1",
        "remove_watchdog_from_startup.bat",
        "start.bat",
        "start_hidden.ps1",
        "start_hidden.vbs",
        "README.md",
        "WATCHDOG_AUTORUN_GUIDE.txt",
        "LICENSE",
        ".gitattributes",
        ".gitignore"
    )
    foreach ($item in $itemsToCopy) {
        $source = Join-Path $SourcePath $item
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $target = Join-Path $TargetPath $item
        if ((Get-Item -LiteralPath $source).PSIsContainer) {
            & robocopy $source $target /MIR /XD "__pycache__" ".pytest_cache" /XF "*.pyc" "*.pyo" /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -gt 7) { throw "Copying folder $item failed (robocopy $LASTEXITCODE)." }
        } else {
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

function Remove-ObsoleteProgramFiles {
    Write-Step "Removing obsolete program folders"
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "production version")
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "produkcni verze")
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
    Write-Step "Stopping running Automat"
    Stop-AutomatIfRunning

    $downloadedSource = Download-GitHubSource $temporaryRoot
    Copy-ProgramFiles $downloadedSource

    Remove-ObsoleteProgramFiles

    Write-Step "Cleaning old temporary files"
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "__pycache__")
    Remove-DirectoryInside $TargetPath (Join-Path $TargetPath ".pytest_cache")

    Write-Step "Checking dependencies"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $TargetPath "install.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation or update failed." }

    Write-Host "`nUpdate from GitHub is complete." -ForegroundColor Green
    Write-Host "The database, screenshots, logs, and browser-independent local data in data were preserved."
    Start-AutomatHidden
} finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
