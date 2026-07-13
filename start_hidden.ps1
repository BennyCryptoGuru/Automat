$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\pythonw.exe")) {
    Start-Process -FilePath (Join-Path $PSScriptRoot "install.bat") -WorkingDirectory $PSScriptRoot
    exit 0
}

$pythonw = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
Start-Process -FilePath $pythonw -ArgumentList @("run.py") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
$watchdogLauncher = Join-Path $PSScriptRoot "watchdog_hidden.ps1"
if (Test-Path -LiteralPath $watchdogLauncher) {
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $watchdogLauncher) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
