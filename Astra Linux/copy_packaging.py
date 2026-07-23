"""Copy user-facing packaging files into Astra Linux/OPC_UA_Gateway/."""
from __future__ import annotations

import shutil
import stat
from pathlib import Path

ASTRA = Path(__file__).resolve().parent
PKG = ASTRA / "packaging"
OUT = ASTRA / "OPC_UA_Gateway"

launch = PKG / "Запуск.sh"
readme = PKG / "README.txt"
binary = OUT / "OPC_UA_Gateway"

if launch.is_file():
    dest = OUT / launch.name
    shutil.copy2(launch, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

if readme.is_file():
    shutil.copy2(readme, OUT / "README.txt")

if binary.is_file():
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

print(f"Updated: {OUT}")
