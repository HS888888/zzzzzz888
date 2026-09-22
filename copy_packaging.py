"""Copy user-facing packaging files into production/MS SERVICE/."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "production" / "packaging"
OUT = ROOT / "production" / "MS SERVICE"

for name in ("Запуск.bat", "Запуск.vbs", "README.txt"):
    src = PKG / name
    if src.is_file():
        shutil.copy2(src, OUT / src.name)

print(f"Updated: {OUT}")
