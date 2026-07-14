@echo off
setlocal
cd /d "%~dp0"

echo Starting Automat installation...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Details are shown above.
  pause
  exit /b 1
)

echo.
echo Installation completed.
echo Start Automat with start.bat
pause
