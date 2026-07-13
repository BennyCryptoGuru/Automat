@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_watchdog_to_startup.ps1"
if errorlevel 1 (
  echo.
  echo Watchdog startup setup failed.
  pause
  exit /b 1
)

echo.
echo Done. The watchdog will start after Windows login.
pause
