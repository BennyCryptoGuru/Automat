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
wscript.exe "%~dp0start_hidden.vbs"
exit /b 0
