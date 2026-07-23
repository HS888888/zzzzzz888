"""Copy user-facing packaging files into production/OPC_UA_Gateway/."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "production" / "packaging"
OUT = ROOT / "production" / "OPC_UA_Gateway"

launch = PKG / "Запуск.bat"
readme = PKG / "README.txt"

if launch.is_file():
    shutil.copy2(launch, OUT / launch.name)
if readme.is_file():
    shutil.copy2(readme, OUT / "README.txt")

print(f"Updated: {OUT}")
