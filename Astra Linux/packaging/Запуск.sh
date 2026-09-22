#!/bin/bash
cd "$(dirname "$0")"
export QTWEBENGINEPROCESS_PATH="$PWD/_internal/PySide6/Qt/libexec/QtWebEngineProcess"
exec ./OPC_UA_Gateway "$@"
