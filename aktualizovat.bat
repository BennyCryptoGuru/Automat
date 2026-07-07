@echo off
setlocal
cd /d "%~dp0"

if not exist "produkcni verze\aktualizovat.bat" (
  echo Aktualizacni skript produkcni verze nebyl nalezen.
  echo Ocekavana cesta: %~dp0produkcni verze\aktualizovat.bat
  pause
  exit /b 1
)

call "produkcni verze\aktualizovat.bat" %*
