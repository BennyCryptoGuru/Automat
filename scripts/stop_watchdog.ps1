$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root

$logDir = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "watchdog-start.log"

function Get-WatchdogProcessIds {
    $escapedRoot = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                ($_.CommandLine -match "watchdog\.py" -and $_.CommandLine -match $escapedRoot) -or
                ($_.CommandLine -match "watchdog_hidden\.ps1" -and $_.CommandLine -match $escapedRoot)
            )
        } |
        Select-Object -ExpandProperty ProcessId |
        Where-Object { $_ -and $_ -ne $PID } |
        Sort-Object -Unique
}

$ids = @(Get-WatchdogProcessIds)
if (-not $ids.Count) {
    Write-Host "Watchdog is not running."
    "[$(Get-Date -Format s)] Manual watchdog stop requested, but no process was running." |
        Add-Content -LiteralPath $logFile -Encoding UTF8
    exit 0
}

foreach ($id in $ids) {
    try {
        Write-Host "Stopping watchdog PID $id"
        Stop-Process -Id $id -Force -ErrorAction Stop
    } catch {
        Write-Warning "Could not stop watchdog PID $id with Stop-Process: $($_.Exception.Message)"
        & taskkill.exe /PID $id /F /T | Out-Null
    }
}

"[$(Get-Date -Format s)] Manual watchdog stop requested. Stopped PIDs: $($ids -join ', ')." |
    Add-Content -LiteralPath $logFile -Encoding UTF8
Write-Host "Watchdog stopped." -ForegroundColor Green
