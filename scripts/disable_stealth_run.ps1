param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$DataDir = Join-Path $Root "data"
$Database = Join-Path $DataDir "automat.db"
$AppUrl = "http://127.0.0.1:5000"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-PythonExecutable {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return (Resolve-Path -LiteralPath $venvPython).Path }
    foreach ($command in @("py", "python", "python3")) {
        if (Get-Command $command -ErrorAction SilentlyContinue) { return $command }
    }
    throw "Python was not found. Run install.bat first."
}

function Set-StealthRunDisabled {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $python = Get-PythonExecutable
    $script = @"
import json
import sqlite3
import sys
from pathlib import Path

database = Path(sys.argv[1])
database.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(database) as connection:
    connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "INSERT INTO settings(key,value) VALUES('stealth_run', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (json.dumps(False),),
    )
"@
    $temporaryScript = Join-Path $env:TEMP "automat_disable_stealth.py"
    Set-Content -LiteralPath $temporaryScript -Value $script -Encoding UTF8
    try {
        if ($python -eq "py") {
            & py -3 $temporaryScript $Database
        } else {
            & $python $temporaryScript $Database
        }
        if ($LASTEXITCODE -ne 0) { throw "Could not update stealth_run in the database." }
    } finally {
        Remove-Item -LiteralPath $temporaryScript -Force -ErrorAction SilentlyContinue
    }
}

function Stop-ControlledBrowser {
    try {
        Invoke-RestMethod -Method Post -Uri "$AppUrl/api/browser/quit" -ContentType "application/json" -Body "{}" -TimeoutSec 3 | Out-Null
        Write-Host "Controlled browser closed."
    } catch {
        Write-Host "Controlled browser API is not available; continuing."
    }
}

function Get-AutomatProcessIds {
    $ids = @()
    try {
        $ids += Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess
    } catch {
    }
    $escapedRoot = [regex]::Escape($Root)
    $ids += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match $escapedRoot -or
                $_.CommandLine -match "AutomatBrowserStudio" -or
                ($_.CommandLine -match "run\.py" -and $_.Name -match "python")
            )
        } |
        Select-Object -ExpandProperty ProcessId
    return $ids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique
}

function Stop-AutomatServer {
    $ids = @(Get-AutomatProcessIds)
    if (-not $ids.Count) {
        Write-Host "Automat server is not running."
        return
    }
    foreach ($id in $ids) {
        try {
            Write-Host "Stopping Automat PID $id"
            Stop-Process -Id $id -Force -ErrorAction Stop
        } catch {
            & taskkill.exe /PID $id /F /T | Out-Null
        }
    }
    Start-Sleep -Seconds 2
}

function Start-AutomatVisible {
    if ($NoRestart) { return }
    $launcher = Join-Path $Root "start.bat"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Start launcher was not found: $launcher"
    }
    Start-Process -FilePath $launcher -WorkingDirectory $Root
    Write-Host "Automat restart requested. Because Stealth run is disabled, the terminal and UI will open visibly."
}

Write-Host "Automat - disable Stealth run" -ForegroundColor Magenta
Write-Step "Writing stealth_run=false"
Set-StealthRunDisabled
Write-Step "Closing controlled browser"
Stop-ControlledBrowser
Write-Step "Restarting Automat"
Stop-AutomatServer
Start-AutomatVisible
Write-Host "`nStealth run is disabled." -ForegroundColor Green
