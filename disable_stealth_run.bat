@echo off
setlocal
cd /d "%~dp0"

if not exist "production version\disable_stealth_run.bat" (
  echo Production stealth helper was not found.
  echo Expected path: %~dp0production version\disable_stealth_run.bat
  pause
  exit /b 1
)

call "production version\disable_stealth_run.bat" %*
