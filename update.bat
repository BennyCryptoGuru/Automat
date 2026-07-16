@echo off
setlocal
cd /d "%~dp0"

echo Starting Automat update...
set "REMOTE_UPDATER=%TEMP%\Automat-update-latest-%RANDOM%%RANDOM%.ps1"
set "UPDATE_SOURCE=%~dp0scripts\update.ps1"

echo Checking latest updater from GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/BennyCryptoGuru/Automat/main/scripts/update.ps1' -OutFile $env:REMOTE_UPDATER -UseBasicParsing; exit 0 } catch { Write-Warning $_.Exception.Message; exit 1 }"
if exist "%REMOTE_UPDATER%" (
  set "UPDATE_SOURCE=%REMOTE_UPDATER%"
) else (
  echo Could not download the latest updater, using local updater.
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%UPDATE_SOURCE%" -TargetPath "%~dp0." %*
if errorlevel 1 (
  echo.
  echo Update failed. Details are shown above.
  if exist "%REMOTE_UPDATER%" del /f /q "%REMOTE_UPDATER%" >nul 2>nul
  pause
  exit /b 1
)

if exist "%REMOTE_UPDATER%" del /f /q "%REMOTE_UPDATER%" >nul 2>nul
echo.
echo Update completed.
timeout /t 2 /nobreak >nul
exit /b 0
