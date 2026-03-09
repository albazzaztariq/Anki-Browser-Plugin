@echo off
REM AJS Uninstaller — called by the MSI during Remove.
REM Removes the Anki add-on and the AJS app data folder.

echo Removing AJS Anki add-on...
if exist "%APPDATA%\Anki2\addons21\ajs_addon" (
    rmdir /s /q "%APPDATA%\Anki2\addons21\ajs_addon"
)

echo Removing AJS app data...
if exist "%APPDATA%\AJS" (
    rmdir /s /q "%APPDATA%\AJS"
)

echo Removing AJS terminal scripts...
if exist "%USERPROFILE%\.ajs\terminal" (
    rmdir /s /q "%USERPROFILE%\.ajs\terminal"
)

echo AJS uninstall complete.
