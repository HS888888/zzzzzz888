#!/bin/bash
# System packages for building and running OPC UA Gateway on Astra Linux SE 1.8.
set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
    echo "Запустите с sudo: sudo $0"
    exit 1
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[ERROR] Только x86_64 поддерживается; обнаружено: $(uname -m)"
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
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

echo "Готово."
echo "Проверка среды: ./preflight.sh"
echo "Проверка исходников: ./validate_source.sh"
echo "Сборка: ./build.sh"
