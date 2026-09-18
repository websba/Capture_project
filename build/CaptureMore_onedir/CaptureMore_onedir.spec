# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a faster-starting onedir CaptureMore build."""

block_cipher = None

hiddenimports = [
    "win32clipboard",
    "win32api",
    "pywintypes",
    "mss",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
]

excludes = [
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "tkinter.test",
    "win32com",
    "pythoncom",
    "comtypes",
]

a = Analysis(
    ["../main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = [
    b
    for b in a.binaries
    if ("pythoncom" not in b[0].lower() and "win32com" not in b[0].lower())
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CaptureMore",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CaptureMore_onedir",
)
