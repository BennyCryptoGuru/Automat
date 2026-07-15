@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_watchdog.ps1"
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
