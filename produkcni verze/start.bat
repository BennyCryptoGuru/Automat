@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Automat zatim neni nainstalovany.
  echo Spoustim instalaci...
  call install.bat
  if errorlevel 1 (
    echo.
    echo Instalace selhala. Automat nelze spustit.
    pause
    exit /b 1
  )
)

echo Spoustim Automat - produkcni verze...
wscript.exe "%~dp0start_hidden.vbs"
exit /b 0
