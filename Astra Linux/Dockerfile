# Build OPC UA Gateway portable bundle (Debian bookworm ≈ Astra Linux 1.7+ base).
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /src

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev build-essential \
    libgl1 libglib2.0-0 libxkbcommon-x11-0 libxcb-cursor0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-randr0 \
    libnss3 libasound2 libxdamage1 libxrandr2 libgbm1 libx11-xcb1 \
    libxcomposite1 libxtst6 libxss1 libfontconfig1 libdbus-1-3 \
    libegl1 libopengl0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-build.txt app.py gateway.py gui_app.py config_manager.py opcua_browse.py paper_ops_app.html ./
COPY emulator ./emulator
COPY ["Astra Linux/build.sh", "Astra Linux/build.sh"]
COPY ["Astra Linux/build_linux.spec", "Astra Linux/build_linux.spec"]
COPY ["Astra Linux/copy_packaging.py", "Astra Linux/copy_packaging.py"]
COPY ["Astra Linux/packaging", "Astra Linux/packaging"]

RUN chmod +x "Astra Linux/build.sh" "Astra Linux/packaging/Запуск.sh" \
    && cd "Astra Linux" && ./build.sh
