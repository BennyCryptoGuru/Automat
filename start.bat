@echo off
setlocal
cd /d "%~dp0"

if not exist "production version\start.bat" (
  echo Production version was not found.
  echo Expected path: %~dp0production version\start.bat
  pause
  exit /b 1
)

wscript.exe "%~dp0production version\start_hidden.vbs"
exit /b 0
