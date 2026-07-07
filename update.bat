@echo off
setlocal
cd /d "%~dp0"

if not exist "production version\update.bat" (
  echo Production update script was not found.
  echo Expected path: %~dp0production version\update.bat
  pause
  exit /b 1
)

call "production version\update.bat" %*
