#!/bin/bash
# Collect build-machine information required for Astra Linux SE 1.8 x86_64.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT="${1:-$SCRIPT_DIR/preflight-report.txt}"

{
    echo "OPC UA Gateway / Astra Linux build preflight"
    echo "Generated: $(date --iso-8601=seconds)"
    echo
    echo "== OS =="
    cat /etc/os-release
    echo
    echo "== Architecture =="
    uname -m
    echo
    echo "== glibc =="
    ldd --version | head -n 1
    echo
    echo "== Python =="
    command -v python3 || true
    python3 --version || true
    echo
    echo "== Display =="
    printf 'DISPLAY=%s\n' "${DISPLAY:-<not set>}"
    printf 'XDG_SESSION_TYPE=%s\n' "${XDG_SESSION_TYPE:-<not set>}"
    echo
    echo "== Required runtime packages =="
    dpkg-query -W -f='${binary:Package}\t${Status}\t${Version}\n' \
        libgl1 libglib2.0-0 libxkbcommon-x11-0 libnss3 libasound2 \
        libgbm1 libx11-xcb1 libxcomposite1 libxtst6 libxss1 \
        libfontconfig1 libdbus-1-3 2>&1 || true
} | tee "$REPORT"

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[ERROR] Expected x86_64 architecture." >&2
    exit 1
fi

if ! grep -qi 'astra' /etc/os-release; then
    echo "[WARN] Astra Linux was not identified in /etc/os-release." >&2
fi

echo "Preflight report: $REPORT"
