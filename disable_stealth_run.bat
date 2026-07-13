@echo off
setlocal
cd /d "%~dp0"

echo Disabling Stealth run and restarting Automat...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0disable_stealth_run.ps1" %*
if errorlevel 1 (
  echo.
  echo Could not disable Stealth run. Details are shown above.
  pause
  exit /b 1
)

echo.
echo Stealth run is disabled. Automat is restarting with a visible window.
timeout /t 2 /nobreak >nul
exit /b 0
