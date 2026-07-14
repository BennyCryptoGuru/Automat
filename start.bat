@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Automat is not installed yet.
  echo Starting installation...
  call install.bat
  if errorlevel 1 (
    echo.
    echo Installation failed. Automat cannot be started.
    pause
    exit /b 1
  )
)

echo Starting Automat...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Automat stopped with an error. Details are shown above.
  pause
  exit /b 1
)
exit /b 0
