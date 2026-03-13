@echo off
setlocal enabledelayedexpansion
REM Deploy ajs_addon to Anki's addons folder and restart Anki. Run from project root.
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "SOURCE=%PROJECT_ROOT%\ajs_addon"
set "DEST=%APPDATA%\Anki2\addons21\ajs_addon"
if not exist "%SOURCE%" (
    echo [ERROR] Add-on source not found: %SOURCE%
    pause
    exit /b 1
)
echo Deploying add-on to Anki...
echo   From: %SOURCE%
echo   To:   %DEST%
if exist "%DEST%" rmdir /s /q "%DEST%"
mkdir "%DEST%" 2>nul
xcopy /e /i /y /q "%SOURCE%\*" "%DEST%\" >nul
if not exist "%DEST%\__init__.py" (
    echo [ERROR] Copy may have failed.
    pause
    exit /b 1
)
echo Restarting Anki...
taskkill /IM anki.exe /F /T 2>nul
set "waited=0"
:wait_dead
timeout /t 1 /nobreak >nul
set "still=0"
tasklist /FI "IMAGENAME eq anki.exe" 2>nul | find /i "anki.exe" >nul && set "still=1"
if !still! equ 0 (
    echo Anki process ended.
    goto launch
)
set /a waited+=1
if !waited! geq 15 (
    echo Timeout waiting for Anki to exit.
    goto launch
)
goto wait_dead
:launch
timeout /t 1 >nul
set "attempt=0"
:start_anki
set /a attempt+=1
echo Starting Anki (attempt !attempt!/3)...
start "" "C:\Users\azt12\AppData\Local\Programs\Anki\anki.exe"
set "w=0"
:wait_anki
timeout /t 1 >nul
set /a w+=1
tasklist /V 2>nul | findstr /i "pythonw.exe" | findstr /i "Anki" >nul && goto anki_found
if !w! lss 15 goto wait_anki
if !attempt! lss 3 (
    echo Anki not detected, retrying...
    goto start_anki
)
echo Timeout: Anki did not start.
goto done
:anki_found
echo Anki is running.
:done
echo.
pause