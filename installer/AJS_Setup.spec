# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[('dist_ajs\\ajs.exe', '.'), ('fzf.exe', '.'), ('C:\\Users\\azt12\\OneDrive\\Documents\\Computing\\Shelved Projects\\Jean Projects\\Anki SBX\\ajs_addon', 'ajs_addon')],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.scrolledtext', 'requests', 'winreg', 'win32com.client', 'pywintypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AJS_Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
