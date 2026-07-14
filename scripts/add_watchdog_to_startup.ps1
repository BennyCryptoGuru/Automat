$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $root "scripts\watchdog_hidden.vbs"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Watchdog launcher was not found: $launcher"
}

$startup = [Environment]::GetFolderPath("Startup")
if ([string]::IsNullOrWhiteSpace($startup)) {
    throw "Could not determine the Startup folder for the current user."
}

$shortcutPath = Join-Path $startup "Automat Watchdog.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$launcher`""
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$shortcut.Description = "Automat Watchdog - starts Automat only when Autorun is enabled"
$shortcut.Save()

Write-Host "Shortcut created:" -ForegroundColor Green
Write-Host $shortcutPath
Write-Host ""
Write-Host "The watchdog can keep running, but it starts Automat only when Autorun is enabled in settings."
