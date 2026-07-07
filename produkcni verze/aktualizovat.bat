@echo off
setlocal
cd /d "%~dp0"

echo Spoustim aktualizaci Automatu...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0aktualizovat.ps1" %*
if errorlevel 1 (
  echo.
  echo Aktualizace selhala. Podrobnosti jsou uvedeny vyse.
  pause
  exit /b 1
)

echo.
echo Aktualizace byla dokoncena.
timeout /t 2 /nobreak >nul
exit /b 0
