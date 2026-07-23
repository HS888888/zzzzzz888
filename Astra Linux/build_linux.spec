# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OPC UA Gateway desktop app (Linux / Astra Linux).

Build (on Linux):
  python3 -m PyInstaller --noconfirm --clean "Astra Linux/build_linux.spec"
Output: dist/OPC_UA_Gateway/  (binary + _internal/*.so)
"""

from pathlib import Path

from PyInstaller.utils.hooks import _collect_submodules, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH).parent

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

hiddenimports += _collect_submodules("asyncua", "warn once")[0]

datas = collect_data_files("asyncua", include_py_files=True)
datas.append((str(ROOT / "paper_ops_app.html"), "."))

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["web_app"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OPC_UA_Gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="OPC_UA_Gateway",
)
