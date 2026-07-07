$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "watchdog-start.log"

if (-not (Test-Path -LiteralPath ".venv\Scripts\pythonw.exe")) {
    "[$(Get-Date -Format s)] Watchdog nebyl spusten: chybi .venv\Scripts\pythonw.exe. Nejdrive spustte install.bat." |
        Add-Content -LiteralPath $logFile -Encoding UTF8
    exit 0
}

$pythonw = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
$watchdog = Join-Path $PSScriptRoot "watchdog.py"
if (-not (Test-Path -LiteralPath $watchdog)) {
    "[$(Get-Date -Format s)] Watchdog nebyl spusten: chybi watchdog.py." |
        Add-Content -LiteralPath $logFile -Encoding UTF8
    exit 0
}

Start-Process -FilePath $pythonw -ArgumentList @($watchdog) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
"[$(Get-Date -Format s)] Watchdog spusten." | Add-Content -LiteralPath $logFile -Encoding UTF8
