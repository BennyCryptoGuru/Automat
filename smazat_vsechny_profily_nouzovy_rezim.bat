@echo off
setlocal EnableExtensions
title Automat - odstraneni vsech starych profilu

set "PROJECT=%~dp0"
set "DATA=%~dp0data"
set "LOG=%~dp0smazat_vsechny_profily_nouzovy_rezim.log"

rem Require an elevated Administrator command prompt.
whoami /groups | findstr /c:"S-1-16-12288" >nul 2>&1
if errorlevel 1 (
    echo Zadam o opravneni spravce...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

reg query "HKLM\SYSTEM\CurrentControlSet\Control\SafeBoot\Option" /v OptionValue >nul 2>&1
if errorlevel 1 (
    echo.
    echo POZOR: Windows zrejme neni spusten v nouzovem rezimu.
    echo Nejprve spustte Windows v nouzovem rezimu a potom tento soubor znovu.
    echo.
    pause
    exit /b 2
)

>"%LOG%" echo Automat full profile cleanup started: %date% %time%

echo Ukoncuji procesy, ktere mohou drzet profily...
for %%P in (chrome.exe brave.exe chromedriver.exe python.exe pythonw.exe BraveCrashHandler.exe BraveCrashHandler64.exe) do (
    taskkill /f /im %%P >>"%LOG%" 2>&1
)

if exist "%DATA%\" (
    echo Odstranuji profilove slozky v data...
    for /d %%D in ("%DATA%\browser-profile*") do call :RemoveProfile "%%~fD"
) else (
    echo Slozka data nebyla nalezena: "%DATA%"
    echo Data directory not found: "%DATA%">>"%LOG%"
)

echo Odstranuji stare docasne profily Automatu z TEMP...
for /d %%D in ("%TEMP%\automat-chrome-*") do call :RemoveProfile "%%~fD"
for /d %%D in ("%TEMP%\automat-brave-*") do call :RemoveProfile "%%~fD"

set "REMAINING=0"
if exist "%DATA%\" (
    for /d %%D in ("%DATA%\browser-profile*") do set "REMAINING=1"
)
for /d %%D in ("%TEMP%\automat-chrome-*") do set "REMAINING=1"
for /d %%D in ("%TEMP%\automat-brave-*") do set "REMAINING=1"

echo.>>"%LOG%"
if "%REMAINING%"=="0" (
    echo HOTOVO: Vsechny stare profilove slozky byly odstraneny.
    echo Success>>"%LOG%"
) else (
    echo CHYBA: Nektere profilove slozky se nepodarilo odstranit.
    echo Podrobnosti jsou v: "%LOG%"
    echo Failed - directories remain>>"%LOG%"
)

echo.
echo Databaze, screenshoty, objekty a workflow nebyly zmeneny.
pause
exit /b

:RemoveProfile
set "TARGET=%~1"
if not exist "%TARGET%\" exit /b
echo Zpracovavam: "%TARGET%"
echo Processing: "%TARGET%">>"%LOG%"
attrib -r -s -h "%TARGET%" /s /d >>"%LOG%" 2>&1
takeown.exe /f "%TARGET%" /r /a /skipsl >>"%LOG%" 2>&1
icacls.exe "%TARGET%" /inheritance:e /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F /t /c /q >>"%LOG%" 2>&1
rd /s /q "%TARGET%" >>"%LOG%" 2>&1
exit /b
