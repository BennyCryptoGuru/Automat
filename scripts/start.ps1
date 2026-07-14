$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$AppUrl = "http://127.0.0.1:5000"

function Test-ServerRunning {
    try {
        $response = Invoke-WebRequest -Uri "$AppUrl/api/bootstrap" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-StealthRunEnabled {
    $database = Join-Path $Root "data\automat.db"
    if (-not (Test-Path -LiteralPath $database)) {
        return $false
    }
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        return $false
    }
    $script = @"
import json
import sqlite3
import sys
from pathlib import Path

database = Path(sys.argv[1])
try:
    with sqlite3.connect(database, timeout=2) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key='stealth_run'").fetchone()
except sqlite3.Error:
    row = None
print("1" if row and bool(json.loads(row[0])) else "0")
"@
    $result = $script | & $python - $database
    return ($result | Select-Object -Last 1) -eq "1"
}

function Start-WatchdogHidden {
    $watchdogLauncher = Join-Path $PSScriptRoot "watchdog_hidden.ps1"
    if (Test-Path -LiteralPath $watchdogLauncher) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $watchdogLauncher) -WorkingDirectory $Root -WindowStyle Hidden
    }
}

if (Test-ServerRunning) {
    if (Test-StealthRunEnabled) {
        Write-Host "Automat is already running in Stealth run mode."
    } else {
        Write-Host "Automat is already running. Opening the existing UI: $AppUrl"
        Start-Process $AppUrl
    }
    exit 0
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Host "Automat is not installed yet. Starting installation..."
    & (Join-Path $Root "install.bat")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (Test-StealthRunEnabled) {
    Write-Host "Stealth run is enabled. Starting Automat in the background."
    $launcher = Join-Path $Root "scripts\start_hidden.vbs"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Hidden launcher was not found: $launcher"
    }
    Start-Process -FilePath "wscript.exe" -ArgumentList @("`"$launcher`"") -WorkingDirectory $Root -WindowStyle Hidden
    exit 0
}

Write-Host "Starting Automat in visible mode."
Write-Host "This terminal stays open while Automat is running."
Write-Host "URL: $AppUrl"
Start-WatchdogHidden
$python = (Resolve-Path ".venv\Scripts\python.exe").Path
& $python (Join-Path $Root "run.py")
