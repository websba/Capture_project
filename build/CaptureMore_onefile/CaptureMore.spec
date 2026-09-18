# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a lean single-file CaptureMore.exe."""

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

# Keep excludes to clearly unused heavy packages only.
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

# Drop COM-related pywin32 binaries; keep pywintypes for clipboard.
a.binaries = [
    b
    for b in a.binaries
    if ("pythoncom" not in b[0].lower() and "win32com" not in b[0].lower())
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CaptureMore",
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
