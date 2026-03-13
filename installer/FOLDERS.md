# Installer folder guide

What each folder under `installer\` is for. **Do not rename** `dist` or `dist_ajs` — `build.bat` expects these exact names.

| Folder       | Created by     | Contains | Safe to delete? |
|-------------|----------------|----------|------------------|
| **dist**    | build.bat Step 3 & 4 | **AJS_Setup.exe** (the installer), **AJS_Setup.msi** (optional). This is the main build output. | No — this is what you ship. |
| **dist_ajs**| build.bat Step 1 | **ajs.exe** (the terminal pipeline). Step 3 bundles this into AJS_Setup.exe. | No — Step 3 needs it. Renaming breaks the build. |
| **build**   | build.bat Step 3 | PyInstaller working files for AJS_Setup (cache, logs, .toc). | Yes — rebuild recreates it. |
| **build_ajs** | build.bat Step 1 | PyInstaller working files for ajs.exe (cache, logs, .toc). | Yes — rebuild recreates it. |

**Other files in `installer\`**

- **ajs.exe** — Copy of `dist_ajs\ajs.exe` (so it sits next to `build.bat`). Not used by the build; for convenience.
- **fzf.exe** — Downloaded by Step 2; bundled into AJS_Setup if present.
- **build.bat** — Run this to build. Uses `dist` and `dist_ajs` by name.
- **installer.py** — Source for the GUI installer (bundled into AJS_Setup.exe).

If you renamed **dist** or **dist_ajs**, rename them back to those exact names, or the next run of `build.bat` will fail or create new folders.
