# AJS — Build Instructions

Produces a single self-contained `AJS_Setup.exe` that installs everything on a user's PC with zero technical knowledge required.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Must be on PATH (`python --version`) |
| pip | Comes with Python |
| Internet connection | To download Ollama, fzf, and the AI model |

## Build (Windows)

```bat
cd installer
build.bat
```

Output: `installer\dist\AJS_Setup.exe`

The script performs these steps automatically:
1. Installs PyInstaller and requests via pip
2. Builds `ajs.exe` from `terminal\ajs.py` (bundles pykakasi, edge-tts, yt-dlp)
3. Downloads `fzf.exe` from GitHub
4. Builds `AJS_Setup.exe` — bundles ajs.exe, fzf.exe, and the ajs_addon folder

## Build (macOS — future)

```bash
cd installer
chmod +x build_mac.sh
./build_mac.sh
```

Output: `installer/dist/AJS_Setup`

## Distribution

Share **only** `installer\dist\AJS_Setup.exe` with users.
The user double-clicks it and the GUI installer handles everything.

## What AJS_Setup.exe does for the user

1. Checks Windows version
2. Downloads and silently installs Ollama
3. Starts the Ollama service
4. Pulls the `qwen2.5:3b` AI model (~2 GB — takes a few minutes)
5. Installs `fzf.exe` to `%APPDATA%\AJS\`
6. Installs `ajs.exe` to `%APPDATA%\AJS\` and adds it to the user PATH
7. Installs the Anki add-on to `%APPDATA%\Anki2\addons21\ajs_addon\`
8. Creates a desktop shortcut

## Troubleshooting builds

- If `pyinstaller` is not found: `pip install pyinstaller`
- If fzf download fails: manually place `fzf.exe` in `installer\` before running `build.bat`
- If the ajs.exe build fails due to missing packages: `pip install pykakasi edge-tts yt-dlp pygetwindow pyperclip`
