@echo off
setlocal
cd /d "%~dp0"

if not exist "produkcni verze\start.bat" (
  echo Produkcni verze nebyla nalezena.
  echo Ocekavana cesta: %~dp0produkcni verze\start.bat
  pause
  exit /b 1
)

wscript.exe "%~dp0produkcni verze\start_hidden.vbs"
exit /b 0
