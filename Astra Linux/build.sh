#!/bin/bash
# Production build for Astra Linux SE 1.8 x86_64: portable folder + _internal.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$SCRIPT_DIR/OPC_UA_Gateway"
SPEC="$SCRIPT_DIR/build_linux.spec"
WORK_DIR="$SCRIPT_DIR/.pyinstaller-build"
DIST_DIR="$SCRIPT_DIR/.pyinstaller-dist"
MAX_ATTEMPTS=5

cd "$PROJECT_ROOT"

echo "=== OPC UA Gateway: Astra Linux production build ==="
echo

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[ERROR] This build supports x86_64 only; detected: $(uname -m)"
    exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[ERROR] $PYTHON_BIN not found. Run: sudo ./install_system_deps.sh"
    exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "[ERROR] Python 3.10+ is required; detected: $PYTHON_VERSION"
    exit 1
fi

echo "[1/7] Creating virtual environment (Python $PYTHON_VERSION)..."
VENV="$SCRIPT_DIR/.build-venv"
if [[ ! -d "$VENV" ]]; then
    "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
PY=python

echo
echo "[2/7] Installing runtime dependencies..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

echo
echo "[3/7] Installing PyInstaller..."
"$PY" -m pip install -r requirements-build.txt

echo
echo "[4/7] Checking Python imports..."
"$PY" -c "import asyncua; from PySide6.QtWebEngineWidgets import QWebEngineView; import gui_app; print('Imports OK')"

echo
echo "[5/7] Building portable folder (may take several minutes)..."
BUILD_OK=0
rm -rf "$WORK_DIR" "$DIST_DIR"
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if [[ "$BUILD_OK" -eq 0 ]]; then
        echo "Attempt $attempt/$MAX_ATTEMPTS..."
        if "$PY" -m PyInstaller --noconfirm --clean \
            --workpath "$WORK_DIR" --distpath "$DIST_DIR" "$SPEC"; then
            if [[ -x "$DIST_DIR/OPC_UA_Gateway/OPC_UA_Gateway" ]]; then
                BUILD_OK=1
            fi
        fi
    fi
done

if [[ "$BUILD_OK" -ne 1 ]]; then
    echo "[ERROR] PyInstaller failed after $MAX_ATTEMPTS attempts"
    exit 1
fi

echo
echo "[6/7] Copying production files..."
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp -a "$DIST_DIR/OPC_UA_Gateway/." "$OUT_DIR/"

echo
echo "[7/7] Adding launcher, README and validating resources..."
"$PY" "$SCRIPT_DIR/copy_packaging.py"

if [[ ! -f "$OUT_DIR/_internal/paper_ops_app.html" ]]; then
    echo "[ERROR] Missing paper_ops_app.html in packaged application"
    exit 1
fi
if ! find "$OUT_DIR/_internal" -type f -name 'QtWebEngineProcess' -print -quit | grep -q .; then
    echo "[ERROR] Missing QtWebEngineProcess in packaged application"
    exit 1
fi

echo
echo "Done."
echo
echo "Production folder:"
echo "  $OUT_DIR/"
echo
echo "  OPC_UA_Gateway  - launch application"
echo "  _internal/      - libraries (.so)"
echo "  Запуск.sh       - shortcut for end user"
echo
echo "Copy the whole OPC_UA_Gateway folder to another Astra Linux PC (no Python required)."
