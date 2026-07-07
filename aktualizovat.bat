@echo off
setlocal
cd /d "%~dp0"

if not exist "production version\aktualizovat.bat" (
  echo Production update script was not found.
  echo Expected path: %~dp0production version\aktualizovat.bat
  pause
  exit /b 1
)

call "production version\aktualizovat.bat" %*
