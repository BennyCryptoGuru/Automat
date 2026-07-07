@echo off
setlocal
cd /d "%~dp0"

echo Spoustim instalaci Automatu...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo Instalace selhala. Podrobnosti jsou uvedeny vyse.
  pause
  exit /b 1
)

echo.
echo Instalace byla dokoncena.
echo Automat spustite souborem start.bat
pause
