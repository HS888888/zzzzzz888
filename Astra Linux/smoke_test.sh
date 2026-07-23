#!/bin/bash
# Verify a completed portable build on an Astra Linux desktop session.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${1:-$SCRIPT_DIR/OPC_UA_Gateway}"
APP="$APP_DIR/OPC_UA_Gateway"

if [[ ! -x "$APP" ]]; then
    echo "[ERROR] Executable not found: $APP"
    exit 1
fi
if [[ ! -f "$APP_DIR/_internal/paper_ops_app.html" ]]; then
    echo "[ERROR] UI resource is missing: _internal/paper_ops_app.html"
    exit 1
fi
if ! find "$APP_DIR/_internal" -type f -name 'QtWebEngineProcess' -print -quit | grep -q .; then
    echo "[ERROR] QtWebEngineProcess is missing from _internal."
    exit 1
fi

echo "== Dynamic library check =="
if ldd "$APP" | grep -F 'not found'; then
    echo "[ERROR] Install the missing system libraries, then rerun this test."
    exit 1
fi
while IFS= read -r -d '' library; do
    if ldd "$library" 2>/dev/null | grep -Fq 'not found'; then
        echo "[ERROR] Missing dependency of: $library"
        ldd "$library" | grep -F 'not found' || true
        exit 1
    fi
done < <(find "$APP_DIR/_internal" -type f \( -name '*.so' -o -name '*.so.*' \) -print0)

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "[ERROR] Run this test from the Astra graphical desktop session."
    exit 1
fi

echo "Launching application for 10 seconds..."
cd "$APP_DIR"
"$APP" >smoke-test.log 2>&1 &
PID=$!
sleep 10

if ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID" || true
    echo "[ERROR] Application closed during startup. See: $APP_DIR/smoke-test.log"
    exit 1
fi

echo "Application is running (PID $PID). Verify in the opened window:"
echo "  1. The diagram and controls are visible."
echo "  2. Click Save; settings.json appears next to the executable."
echo "  3. Start and stop the built-in test/emulator; logs/gateway.log appears."
echo "Press Enter after the manual check to close the test process."
read -r
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true

echo "Smoke test completed."
