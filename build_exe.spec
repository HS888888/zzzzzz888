# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OPC UA Gateway desktop app (Windows).

Build: python -m PyInstaller --noconfirm --clean build_exe.spec
Output: dist/OPC_UA_Gateway/  (exe + _internal/*.dll)
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, _collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

hiddenimports = [
    "config_manager",
    "gateway",
    "gui_app",
    "opcua_browse",
    "asyncio",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
    "shiboken6",
    "sortedcontainers",
    "aiosqlite",
    "cryptography",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.bindings._rust",
    "cryptography.x509",
]

# Call _collect_submodules directly (main process) — collect_submodules() uses an isolated
# subprocess that can crash on Python 3.14 / Windows.
hiddenimports += _collect_submodules("asyncua", "warn once")[0]

datas = collect_data_files("asyncua", include_py_files=True)
datas.append((str(ROOT / "paper_ops_app.html"), "."))
datas.append((str(ROOT / "app_icon.ico"), "."))
datas.append((str(ROOT / "app_icon.png"), "."))
# PySide6 / Qt WebEngine binaries and resources are collected by PyInstaller hooks
# when analyzing gui_app imports (do not bundle all of PySide6 — breaks on Python 3.14).

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["web_app"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MS SERVICE",
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
    icon=str(ROOT / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MS SERVICE",
)
