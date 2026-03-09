@echo off
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║            AJS Build Script — Windows               ║
echo ║  Produces: installer\dist\AJS_Setup.exe             ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: ── Resolve project root (one level above this script) ──
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
pushd "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"
popd

echo [AJS Build] Project root : %PROJECT_ROOT%
echo [AJS Build] Installer dir: %SCRIPT_DIR%
echo.

:: ── Prerequisites ──
echo [AJS Build] Installing/upgrading PyInstaller and requests...
pip install --upgrade pyinstaller requests
if errorlevel 1 (
    echo [AJS Build] ERROR: pip install failed. Make sure Python and pip are on PATH.
    exit /b 1
)

:: ── Step 1: Build ajs.exe from terminal\ajs.py ──
echo.
echo [AJS Build] Step 1: Building ajs.exe...
cd /d "%PROJECT_ROOT%"
pyinstaller ^
    --onefile ^
    --name ajs ^
    --distpath "%SCRIPT_DIR%dist_ajs" ^
    --workpath "%SCRIPT_DIR%build_ajs" ^
    --specpath "%SCRIPT_DIR%" ^
    terminal\ajs.py ^
    --hidden-import pykakasi ^
    --hidden-import edge_tts ^
    --hidden-import yt_dlp ^
    --hidden-import pygetwindow ^
    --hidden-import pyperclip ^
    --hidden-import requests ^
    --collect-all pykakasi ^
    --collect-all edge_tts ^
    --collect-all yt_dlp

if errorlevel 1 (
    echo [AJS Build] ERROR: ajs.exe build failed.
    exit /b 1
)
echo [AJS Build] ajs.exe built: %SCRIPT_DIR%dist_ajs\ajs.exe

:: ── Step 2: Download fzf.exe ──
echo.
echo [AJS Build] Step 2: Downloading fzf.exe...
set "FZF_URL=https://github.com/junegunn/fzf/releases/latest/download/fzf-windows-amd64.zip"
set "FZF_ZIP=%SCRIPT_DIR%fzf.zip"
set "FZF_EXE=%SCRIPT_DIR%fzf.exe"

if exist "%FZF_EXE%" (
    echo [AJS Build] fzf.exe already present — skipping download.
) else (
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri '%FZF_URL%' -OutFile '%FZF_ZIP%'; Expand-Archive -Path '%FZF_ZIP%' -DestinationPath '%SCRIPT_DIR%' -Force"
    if errorlevel 1 (
        echo [AJS Build] WARNING: fzf download failed. AJS_Setup.exe will download fzf at install time.
    ) else (
        echo [AJS Build] fzf.exe extracted to %SCRIPT_DIR%
    )
)

:: ── Step 3: Build AJS_Setup.exe ──
echo.
echo [AJS Build] Step 3: Building AJS_Setup.exe...
cd /d "%SCRIPT_DIR%"

:: Build the --add-data arguments dynamically so we can handle missing fzf gracefully.
set "EXTRA_DATA="
if exist "%SCRIPT_DIR%dist_ajs\ajs.exe" (
    set "EXTRA_DATA=!EXTRA_DATA! --add-data "dist_ajs\ajs.exe;.""
)
if exist "%SCRIPT_DIR%fzf.exe" (
    set "EXTRA_DATA=!EXTRA_DATA! --add-data "fzf.exe;.""
)

pyinstaller ^
    --onefile ^
    --name AJS_Setup ^
    --windowed ^
    --distpath "%SCRIPT_DIR%dist" ^
    --workpath "%SCRIPT_DIR%build" ^
    --specpath "%SCRIPT_DIR%" ^
    installer.py ^
    %EXTRA_DATA% ^
    --add-data "%PROJECT_ROOT%\ajs_addon;ajs_addon" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.scrolledtext ^
    --hidden-import requests ^
    --hidden-import winreg ^
    --hidden-import win32com.client ^
    --hidden-import pywintypes

if errorlevel 1 (
    echo [AJS Build] ERROR: AJS_Setup.exe build failed.
    exit /b 1
)

:: ── Step 4: Build AJS_Setup.msi (requires WiX v4) ──
echo.
echo [AJS Build] Step 4: Building AJS_Setup.msi...

where wix >nul 2>&1
if errorlevel 1 (
    echo [AJS Build] WiX not found — installing via dotnet tool...
    dotnet tool install --global wix
    if errorlevel 1 (
        echo [AJS Build] ERROR: Could not install WiX. Install .NET SDK from https://dot.net then re-run.
        exit /b 1
    )
)

cd /d "%SCRIPT_DIR%"
wix build ajs.wxs -out dist\AJS_Setup.msi

if errorlevel 1 (
    echo [AJS Build] ERROR: MSI build failed.
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  Build complete!                                     ║
echo ║  Output: installer\dist\AJS_Setup.msi               ║
echo ║  Share ONLY that single file with users.            ║
echo ╚══════════════════════════════════════════════════════╝
echo.
