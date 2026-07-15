@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_watchdog.ps1"
if errorlevel 1 (
  echo.
  echo Watchdog stop failed.
  pause
  exit /b 1
)

echo.
echo Watchdog stop completed.
timeout /t 2 /nobreak >nul
exit /b 0
