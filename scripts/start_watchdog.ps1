$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root

$logDir = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "watchdog-start.log"

$pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Missing .venv\Scripts\pythonw.exe. Run install.bat first."
}

$watchdog = Join-Path $PSScriptRoot "watchdog.py"
if (-not (Test-Path -LiteralPath $watchdog)) {
    throw "Missing watchdog.py: $watchdog"
}

Start-Process -FilePath $pythonw -ArgumentList @($watchdog) -WorkingDirectory $Root -WindowStyle Hidden
"[$(Get-Date -Format s)] Manual watchdog start requested." | Add-Content -LiteralPath $logFile -Encoding UTF8
Write-Host "Watchdog start requested. It will only start Automat when Autorun is enabled." -ForegroundColor Green
