$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$launcher = Join-Path $root "watchdog_hidden.vbs"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Nenalezen launcher watchdogu: $launcher"
}

$startup = [Environment]::GetFolderPath("Startup")
if ([string]::IsNullOrWhiteSpace($startup)) {
    throw "Nepodarilo se zjistit slozku Po spusteni pro aktualniho uzivatele."
}

$shortcutPath = Join-Path $startup "Automat Watchdog.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$launcher`""
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$shortcut.Description = "Automat Watchdog - starts production Automat only when Autorun is enabled"
$shortcut.Save()

Write-Host "Zastupce vytvoren:" -ForegroundColor Green
Write-Host $shortcutPath
Write-Host ""
Write-Host "Watchdog muze bezet porad, ale Automat spusti jen pokud je v nastaveni zapnuty Autorun."
