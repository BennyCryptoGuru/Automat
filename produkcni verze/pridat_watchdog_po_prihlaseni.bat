@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0pridat_watchdog_po_prihlaseni.ps1"
if errorlevel 1 (
  echo.
  echo Nastaveni watchdogu po prihlaseni selhalo.
  pause
  exit /b 1
)

echo.
echo Hotovo. Watchdog se bude spoustet po prihlaseni do Windows.
pause
