#!/bin/bash
# Download OPC UA Gateway from GitHub Releases, install runtime deps, unpack, run.
set -euo pipefail

GITHUB_REPO="${GITHUB_REPO:-HS888888/zzzzzz888}"
RELEASE_TAG="${RELEASE_TAG:-latest}"
ARCHIVE_NAME="opcua-gateway-astra-se18-x86_64.tar.gz"
CHECKSUM_NAME="${ARCHIVE_NAME}.sha256"
INSTALL_DIR="${INSTALL_DIR:-$HOME/OPC_UA_Gateway}"
SKIP_DEPS=0
SKIP_RUN=0
DOWNLOAD_URL=""
CHECKSUM_URL=""

usage() {
    cat <<'EOF'
Установка OPC UA Gateway на Astra Linux SE 1.8 (x86_64)

Использование:
  sudo bash install-opc-gateway.sh [опции]

Не запускайте двойным щелчком — после флешки Windows нужен терминал.

Опции:
  --install-dir PATH   Куда распаковать (по умолчанию: ~/OPC_UA_Gateway)
  --repo OWNER/NAME    GitHub-репозиторий (по умолчанию: HS888888/zzzzzz888)
  --release TAG        Тег релиза или latest (по умолчанию: latest)
  --url URL            Прямая ссылка на .tar.gz (минуя GitHub Releases)
  --no-deps            Не ставить apt-пакеты
  --no-run             Не запускать программу после установки
  -h, --help           Справка

Примеры:
  sudo bash install-opc-gateway.sh
  sed -i 's/\r$//' *.sh && sudo bash install-opc-gateway.sh
  sudo bash install-opc-gateway.sh --url /media/usb/opcua-gateway-astra-se18-x86_64.tar.gz

После установки:
  cd ~/OPC_UA_Gateway && ./Запуск.sh
EOF
}

log() {
    printf '[install] %s\n' "$*"
}

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Не найдена команда: $1"
}

fix_crlf_in_dir() {
    local script_dir="$1"
    local f

    for f in install-opc-gateway.sh install_runtime_deps.sh; do
        if [[ -f "$script_dir/$f" ]] && grep -q $'\r' "$script_dir/$f" 2>/dev/null; then
            sed -i 's/\r$//' "$script_dir/$f"
            log "Исправлены переводы строк Windows (CRLF) в $f"
        fi
    done
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --repo)
                GITHUB_REPO="$2"
                shift 2
                ;;
            --release)
                RELEASE_TAG="$2"
                shift 2
                ;;
            --url)
                DOWNLOAD_URL="$2"
                shift 2
                ;;
            --no-deps)
                SKIP_DEPS=1
                shift
                ;;
            --no-run)
                SKIP_RUN=1
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            *)
                die "Неизвестный аргумент: $1 (см. --help)"
                ;;
        esac
    done
}

check_platform() {
    [[ "$(uname -s)" == "Linux" ]] || die "Скрипт только для Linux."
    [[ "$(uname -m)" == "x86_64" ]] || die "Нужна архитектура x86_64, обнаружено: $(uname -m)"
}

install_runtime_deps() {
    local script_dir deps_script
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    deps_script="$script_dir/install_runtime_deps.sh"

    if [[ -f "$deps_script" ]]; then
        log "Установка системных библиотек..."
        bash "$deps_script"
        return
    fi

    log "install_runtime_deps.sh не найден, ставим пакеты напрямую..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ca-certificates curl wget \
        libgl1 libglib2.0-0 libxkbcommon-x11-0 libxcb-cursor0 \
        libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
        libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-randr0 \
        libnss3 libasound2 libxdamage1 libxrandr2 libgbm1 libx11-xcb1 \
        libxcomposite1 libxtst6 libxss1 libfontconfig1 libdbus-1-3 \
        libegl1 libopengl0
}

resolve_release_urls() {
    local api_url asset_base

    if [[ -n "$DOWNLOAD_URL" ]]; then
        CHECKSUM_URL="${DOWNLOAD_URL}.sha256"
        return
    fi

    need_cmd curl

    if [[ "$RELEASE_TAG" == "latest" ]]; then
        api_url="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
    else
        api_url="https://api.github.com/repos/${GITHUB_REPO}/releases/tags/${RELEASE_TAG}"
    fi

    log "Поиск релиза: $api_url"
    asset_base="$(
        curl -fsSL -H "Accept: application/vnd.github+json" "$api_url" \
            | grep -F "browser_download_url" \
            | grep -F "$ARCHIVE_NAME" \
            | head -n 1 \
            | sed -n 's/.*"browser_download_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
    )"

    [[ -n "$asset_base" ]] || die "Архив ${ARCHIVE_NAME} не найден в релизе. Запустите сборку на GitHub Actions или укажите --url."

    DOWNLOAD_URL="$asset_base"
    CHECKSUM_URL="${DOWNLOAD_URL}.sha256"
}

download_and_verify() {
    local tmp_dir archive checksum_file

    need_cmd wget
    need_cmd sha256sum

    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' EXIT

    archive="$tmp_dir/$ARCHIVE_NAME"
    checksum_file="$tmp_dir/$CHECKSUM_NAME"

    log "Скачивание: $DOWNLOAD_URL"
    wget -q --show-progress -O "$archive" "$DOWNLOAD_URL"

    log "Скачивание контрольной суммы..."
    if wget -q -O "$checksum_file" "$CHECKSUM_URL" 2>/dev/null; then
        (
            cd "$tmp_dir"
            sha256sum -c "$CHECKSUM_NAME"
        )
        log "Контрольная сумма OK."
    else
        log "Файл .sha256 не найден — пропуск проверки."
    fi

    install_archive "$archive"
}

install_archive() {
    local archive="$1"
    local parent_dir extracted_dir backup_dir

    extracted_dir="OPC_UA_Gateway"
    parent_dir="$(dirname "$INSTALL_DIR")"
    mkdir -p "$parent_dir"

    if [[ -d "$INSTALL_DIR" ]]; then
        backup_dir="${INSTALL_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
        log "Резервная копия: $backup_dir"
        mv "$INSTALL_DIR" "$backup_dir"
    fi

    log "Распаковка в $parent_dir ..."
    tar -xzf "$archive" -C "$parent_dir"

    if [[ "$parent_dir/$extracted_dir" != "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        mv "$parent_dir/$extracted_dir" "$INSTALL_DIR"
    fi

    chmod +x "$INSTALL_DIR/Запуск.sh" "$INSTALL_DIR/OPC_UA_Gateway" 2>/dev/null || true

    log "Установлено: $INSTALL_DIR"
}

run_app() {
    if [[ "$SKIP_RUN" -eq 1 ]]; then
        log "Запуск пропущен (--no-run)."
        log "Команда: cd \"$INSTALL_DIR\" && ./Запуск.sh"
        return
    fi

    if [[ -n "${DISPLAY:-}" ]] || [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        log "Запуск программы..."
        (cd "$INSTALL_DIR" && exec ./Запуск.sh)
    else
        log "GUI не обнаружен (нет DISPLAY). Запустите вручную:"
        log "  cd \"$INSTALL_DIR\" && ./Запуск.sh"
    fi
}

main() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fix_crlf_in_dir "$script_dir"

    parse_args "$@"
    check_platform

    if [[ "$SKIP_DEPS" -eq 0 ]]; then
        if [[ "${EUID:-0}" -ne 0 ]]; then
            die "Для установки библиотек нужен root: sudo bash $0 $*"
        fi
        install_runtime_deps
    else
        need_cmd wget
        need_cmd curl
    fi

    resolve_release_urls
    download_and_verify
    run_app

    cat <<EOF

Готово.
  Папка:   $INSTALL_DIR
  Запуск:  cd "$INSTALL_DIR" && ./Запуск.sh

В программе: настройте ПЛК -> «Сохранить» -> «Запуск».
EOF
}

main "$@"
