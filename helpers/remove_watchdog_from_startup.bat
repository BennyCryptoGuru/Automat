@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path ([Environment]::GetFolderPath('Startup')) 'Automat Watchdog.lnk'; if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Force; Write-Host 'Watchdog shortcut removed:' $p -ForegroundColor Green}else{Write-Host 'Watchdog shortcut was not found in the Startup folder.'}"
echo.
pause
