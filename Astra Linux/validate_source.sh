#!/bin/bash
# Validate dependencies and imports before freezing the application on Astra Linux.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$SCRIPT_DIR/.source-venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[ERROR] Expected x86_64; detected: $(uname -m)"
    exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[ERROR] $PYTHON_BIN not found."
    exit 1
fi

if [[ ! -d "$VENV" ]]; then
    "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m compileall -q app.py config_manager.py gateway.py gui_app.py opcua_browse.py
python -c "import asyncua; from PySide6.QtWebEngineWidgets import QWebEngineView; import gui_app; print('Source imports: OK')"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "[WARN] No graphical session detected. Imports passed, but GUI must be tested from the Astra desktop session."
else
    echo "Imports passed. Start manual GUI test now with:"
    echo "  source \"$VENV/bin/activate\" && python app.py"
fi
