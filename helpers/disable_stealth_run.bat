@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo Disabling Stealth run and restarting Automat...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\disable_stealth_run.ps1" %*
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
