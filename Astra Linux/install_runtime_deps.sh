#!/bin/bash
# Runtime libraries for OPC UA Gateway on Astra Linux SE 1.8 (no Python/build tools).
set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "Запустите с sudo: sudo bash $0"
    exit 1
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[ERROR] Только x86_64 поддерживается; обнаружено: $(uname -m)"
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    ca-certificates \
    curl \
    wget \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-randr0 \
    libnss3 \
    libasound2 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxtst6 \
    libxss1 \
    libfontconfig1 \
    libdbus-1-3 \
    libegl1 \
    libopengl0

echo "Системные библиотеки установлены."
