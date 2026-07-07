@echo off
setlocal
cd /d "%~dp0"

echo Starting Automat update...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
if errorlevel 1 (
  echo.
  echo Update failed. Details are shown above.
  pause
  exit /b 1
)

echo.
echo Update completed.
timeout /t 2 /nobreak >nul
exit /b 0
