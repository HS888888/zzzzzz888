#!/bin/bash
# Create a distributable archive and checksum from a verified portable folder.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/OPC_UA_Gateway"
RELEASE_DIR="$SCRIPT_DIR/release"
ARCHIVE="$RELEASE_DIR/opcua-gateway-astra-se18-x86_64.tar.gz"

if [[ ! -x "$APP_DIR/OPC_UA_Gateway" ]]; then
    echo "[ERROR] Build the application first: ./build.sh"
    exit 1
fi

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# Runtime state must not be shipped to a customer.
rm -rf "$APP_DIR/logs" "$APP_DIR/settings.json" "$APP_DIR/smoke-test.log"

tar -C "$SCRIPT_DIR" -czf "$ARCHIVE" OPC_UA_Gateway
(
    cd "$RELEASE_DIR"
    sha256sum "$(basename "$ARCHIVE")" >"$(basename "$ARCHIVE").sha256"
)

echo "Archive: $ARCHIVE"
echo "Checksum: $ARCHIVE.sha256"
