@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\stop_watchdog.ps1"
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
