$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$AppUrl = "http://127.0.0.1:5000"

try {
    $response = Invoke-WebRequest -Uri "$AppUrl/api/bootstrap" -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -eq 200) {
        Start-Process $AppUrl
        exit 0
    }
} catch {
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\pythonw.exe")) {
    Start-Process -FilePath (Join-Path $Root "install.bat") -WorkingDirectory $Root
    exit 0
}

$pythonw = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
Start-Process -FilePath $pythonw -ArgumentList @((Join-Path $Root "run.py")) -WorkingDirectory $Root -WindowStyle Hidden
$watchdogLauncher = Join-Path $PSScriptRoot "watchdog_hidden.ps1"
if (Test-Path -LiteralPath $watchdogLauncher) {
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $watchdogLauncher) -WorkingDirectory $Root -WindowStyle Hidden
}
