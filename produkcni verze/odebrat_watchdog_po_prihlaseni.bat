@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path ([Environment]::GetFolderPath('Startup')) 'Automat Watchdog.lnk'; if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -Force; Write-Host 'Zastupce watchdogu byl odebran:' $p -ForegroundColor Green}else{Write-Host 'Zastupce watchdogu ve slozce Po spusteni nebyl nalezen.'}"
echo.
pause
