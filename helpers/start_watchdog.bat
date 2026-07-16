@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_watchdog.ps1"
if errorlevel 1 (
  echo.
  echo Watchdog start failed.
  pause
  exit /b 1
)

echo.
echo Watchdog start requested.
timeout /t 2 /nobreak >nul
exit /b 0
