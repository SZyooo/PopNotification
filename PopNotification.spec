# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

datas = [
    ("lang/*.json", "lang"),
    ("ICON.png", "."),
    ("ICON.ico", "."),
]

a = Analysis(
    ["main.py"],
    pathex=[os.path.dirname(__file__)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PIL",
        "PIL._tkinter_finder",
        "pystray",
        "ctypes",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "unittest",
        "email",
        "http",
        "xml",
        "pdb",
        "doctest",
        "turtle",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PopNotification",
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
    icon="ICON.ico",
)
