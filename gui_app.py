"""Native PySide6 desktop GUI for the OPC UA Gateway — diagram-first UX."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QPoint, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QGridLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config_manager import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOCAL_SERVER,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_RECONNECT_INTERVAL,
    auto_create_local_variables,
    build_config_dict,
    load_config_or_default,
    local_server_url_from_port,
    parse_local_port,
    save_config,
)
from gateway import OpcUaGateway, setup_logging
from opcua_browse import (
    OpcUaBrowserSession,
    resolve_tag_list_entries_async,
    test_opcua_connection_async,
    verify_opcua_tags_async,
)

# Paper Ops palette — soft, near-white, minimalist
COLORS = {
    "bg": "#F6F7F8",
    "surface": "#FFFFFF",
    "surface2": "#F4F6F9",
    "header": "#1C1917",
    "header_text": "#FAFAF9",
    "header_muted": "#A8A29E",
    "border": "#E7E9EC",
    "border_light": "#E7E9EC",
    "text": "#1C1917",
    "text_secondary": "#44403C",
    "text_muted": "#78716C",
    "accent": "#1C1917",
    "accent_dark": "#292524",
    "dialog_frame": "#1C1917",
    "dialog_backdrop": "#E4E2DF",
    "plc": "#16A34A",
    "plc_bg": "#FFFFFF",
    "plc_border": "#E7E9EC",
    "gateway": "#1C1917",
    "gateway_bg": "#FFFFFF",
    "gateway_border": "#E7E5E1",
    "customer": "#2563EB",
    "customer_bg": "#FFFFFF",
    "customer_border": "#E7E9EC",
    "success": "#15803D",
    "warning": "#B45309",
    "danger": "#B91C1C",
    "danger_bg": "#FFFFFF",
    "danger_border": "#FECACA",
    "secondary_bg": "#FFFFFF",
    "secondary_text": "#44403C",
    "secondary_border": "#D6D3D1",
    "idle": "#94A3B8",
    "idle_bg": "#F8FAFC",
    "log_bg": "#F5F5F4",
    "log_text": "#57534E",
    "diagram_bg": "#FFFFFF",
    "shadow": "#1C191712",
}

logger = logging.getLogger(__name__)

BLOCK_PLC = "plc"
BLOCK_GATEWAY = "gateway"
BLOCK_CUSTOMER = "customer"

DEFAULT_BLOCK_STATUS: dict[str, Any] = {
    "plcs": [False, False, False],
    "gateway_ok": False,
    "customer_ok": False,
}

FONT_UI = "Segoe UI"
FONT_MONO = "Consolas"


APP_NAME = "OPC UA Gateway"
AUTO_RESTART_DELAY_MS = 5000
AUTO_RESTART_RETRY_MS = 15000


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OPCUA.Gateway.Desktop.1")
    except (AttributeError, OSError):
        pass


def _build_app_icon() -> QIcon:
    icon_path = resource_path("app_icon.ico")
    if icon_path.exists():
        return QIcon(str(icon_path))

    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(COLORS["gateway"]))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(6, 6, size - 12, size - 12, 14, 14)
    painter.setPen(QColor(COLORS["header_text"]))
    font = QFont(FONT_UI, 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()
    return QIcon(pixmap)


def _configure_application(app: QApplication) -> None:
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(_build_app_icon())


def _inherit_app_icon(widget: QWidget) -> None:
    app = QApplication.instance()
    if isinstance(app, QApplication) and not app.windowIcon().isNull():
        widget.setWindowIcon(app.windowIcon())


def _init_settings_dialog(dialog: QDialog) -> None:
    dialog.setWindowTitle("")
    dialog.setWindowIcon(QIcon())


class SettingsDialog(QDialog):
    """Frameless settings panel — Windows Light style (variant 5)."""

    def __init__(self, parent: QWidget | None = None, *, chrome_title: str = "") -> None:
        super().__init__(parent)
        _init_settings_dialog(self)
        self.setObjectName("settingsDialogRoot")
        self._drag_offset: QPoint | None = None
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._panel = QFrame()
        self._panel.setObjectName("dialogPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._panel)

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(1, 1, 1, 1)
        panel_layout.setSpacing(0)

        chrome = QWidget()
        chrome.setObjectName("dialogChrome")
        chrome.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chrome.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chrome.setFixedHeight(32)
        chrome_layout = QHBoxLayout(chrome)
        chrome_layout.setContentsMargins(12, 0, 12, 0)
        chrome_layout.setSpacing(6)

        title_label = QLabel(chrome_title)
        title_label.setObjectName("dialogChromeTitle")
        title_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._chrome_title_label = title_label
        chrome_layout.addWidget(title_label, 1)
        panel_layout.addWidget(chrome)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(20, 12, 20, 20)
        self._content_layout.setSpacing(10)
        self._content_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        panel_layout.addLayout(self._content_layout)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_chrome_title(self, text: str) -> None:
        self._chrome_title_label.setText(text.strip() or "Настройки")

    def _interactive_widget(self, widget: QWidget | None) -> bool:
        current = widget
        while current is not None and current is not self:
            if isinstance(
                current,
                (QLineEdit, QPushButton, QTextEdit, QCheckBox, QAbstractItemView, QSplitter, QScrollArea),
            ):
                return True
            current = current.parentWidget()
        return False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._interactive_widget(self.childAt(event.position().toPoint()))
        ):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


def block_colors(ok: bool, ok_fill: str, ok_border: str) -> tuple[str, str]:
    """Return fill/border for a diagram block based on runtime status."""
    if ok:
        return ok_fill, ok_border
    return COLORS["danger_bg"], COLORS["danger_border"]


def action_hint_style(kind: str = "muted") -> str:
    palette = {
        "muted": COLORS["text_muted"],
        "success": COLORS["success"],
        "danger": COLORS["danger"],
        "accent": COLORS["accent"],
        "warning": COLORS["warning"],
    }
    return f"color: {palette.get(kind, COLORS['text_muted'])}; font-size: 10px; background: transparent;"


def opc_host_port_key(url: str) -> str:
    """Normalize opc.tcp URL to host:port for status lookup."""
    match = re.match(r"opc\.tcp://([^:/]+):(\d+)", (url or "").strip(), re.I)
    if match:
        return f"{match.group(1).lower()}:{match.group(2)}"
    return (url or "").strip().lower().rstrip("/")


def find_plc_status_entry(plc_entries: dict[str, Any], url: str) -> dict[str, Any]:
    """Find PLC runtime status even if URL strings differ slightly."""
    if not url:
        return {}
    direct = plc_entries.get(url)
    if direct:
        return direct
    trimmed = url.rstrip("/")
    for key, value in plc_entries.items():
        if key.rstrip("/") == trimmed:
            return value
    target = opc_host_port_key(url)
    if not target:
        return {}
    for key, value in plc_entries.items():
        if opc_host_port_key(key) == target:
            return value
    return {}


def plc_has_fresh_data(entry: dict[str, Any], stale_limit: float) -> bool:
    """True when the gateway recently read at least one tag from this PLC."""
    last_read = entry.get("last_read")
    if last_read is None:
        return False
    try:
        age = time.monotonic() - float(last_read)
    except (TypeError, ValueError):
        return False
    return age <= stale_limit


def plc_stale_limit(polling_interval: float, node_count: int) -> float:
    """How long to wait before marking a PLC as stale (depends on tag count)."""
    return max(polling_interval * 3 + node_count * 2.0, 20.0)


def plc_is_configured(server: dict[str, Any] | None) -> bool:
    """PLC slot participates in diagram coloring when URL and tags are set."""
    if not server:
        return False
    url = str(server.get("url", "")).strip()
    nodes = server.get("nodes") or []
    return bool(url) and bool(nodes)


def evaluate_diagram_status(
    gw_status: dict[str, Any],
    remote_servers: list[dict[str, Any]],
    polling_interval: float,
) -> dict[str, Any]:
    """Map gateway.get_status() to per-block OK flags for the diagram."""
    running = bool(gw_status.get("running"))
    plc_entries = gw_status.get("plcs", {})

    plcs_ok: list[bool] = []
    plcs_configured: list[bool] = []

    for server in remote_servers[:3]:
        configured = plc_is_configured(server)
        plcs_configured.append(configured)
        if not configured:
            plcs_ok.append(False)
            continue

        url = str(server.get("url", "")).strip()
        nodes = server.get("nodes") or []
        entry = find_plc_status_entry(plc_entries, url)
        stale_limit = plc_stale_limit(polling_interval, len(nodes))

        if not running:
            plcs_ok.append(False)
            continue

        plcs_ok.append(plc_has_fresh_data(entry, stale_limit))

    while len(plcs_ok) < 3:
        plcs_ok.append(False)
    while len(plcs_configured) < 3:
        plcs_configured.append(False)

    local_ok = running and bool(gw_status.get("local_server_ok")) and not gw_status.get("error")
    gateway_ok = local_ok
    customer_ok = local_ok

    return {
        "plcs": plcs_ok,
        "plcs_configured": plcs_configured,
        "gateway_ok": gateway_ok,
        "customer_ok": customer_ok,
    }


def url_to_host_port(url: str) -> str:
    """Extract host:port from opc.tcp URL for diagram labels."""
    match = re.match(r"opc\.tcp://([^:/]+):(\d+)", url or "", re.I)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    trimmed = (url or "").replace("opc.tcp://", "")
    return trimmed or "—"


def gateway_host_port(payload: dict[str, Any]) -> str:
    """Host:port label for the local gateway block on the diagram."""
    port = int(payload.get("local_port", 4841) or 4841)
    namespace_uri = str(payload.get("namespace_uri", DEFAULT_LOCAL_SERVER["namespace_uri"])).strip()
    ip = ip_from_namespace_uri(namespace_uri) or local_ip_hint()
    return f"{ip}:{port}"


def default_plc_server(index: int) -> dict[str, Any]:
    """Default remote server entry for PLC index 0..2."""
    idx = index + 1
    return {
        "name": f"ПЛК #{idx}",
        "url": f"opc.tcp://192.168.1.{9 + idx}:4840",
        "nodes": [
            {"node_id": "ns=2;i=1001", "local_node_id": f"BHK1_PLC{idx}_Temperature"},
            {"node_id": "ns=2;i=1002", "local_node_id": f"BHK1_PLC{idx}_Pressure"},
        ],
    }


def plc_display_name(server: dict[str, Any] | None, index: int) -> str:
    """Human-readable PLC label for diagram and dialog chrome."""
    if server is not None:
        name = str(server.get("name", "")).strip()
        if name:
            return name
    return f"ПЛК #{index + 1}"


def payload_to_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate UI payload and build gateway configuration."""
    remote_servers = payload.get("remote_servers", [])
    if not remote_servers:
        raise ValueError("Добавьте хотя бы один ПЛК")

    for server in remote_servers:
        if not str(server.get("url", "")).strip():
            raise ValueError(f"Не указан URL для ПЛК «{server.get('name', '')}»")
        if not server.get("nodes"):
            raise ValueError(
                f"Нет переменных для ПЛК «{server.get('name', server.get('url'))}»"
            )

    local_port = int(payload.get("local_port", 4841))
    if local_port < 1 or local_port > 65535:
        raise ValueError("Порт локального сервера: от 1 до 65535")

    polling = float(payload.get("polling_interval", DEFAULT_POLLING_INTERVAL))
    reconnect = float(payload.get("reconnect_interval", DEFAULT_RECONNECT_INTERVAL))
    if polling <= 0:
        raise ValueError("Интервал опроса должен быть больше 0")
    if reconnect <= 0:
        raise ValueError("Интервал переподключения должен быть больше 0")

    local_server = {
        "url": local_server_url_from_port(local_port),
        "namespace_uri": str(payload.get("namespace_uri", DEFAULT_LOCAL_SERVER["namespace_uri"])).strip(),
        "folder_name": str(payload.get("folder_name", "GatewayData")).strip() or "GatewayData",
        "variables": auto_create_local_variables(remote_servers),
    }
    if not local_server["variables"]:
        raise ValueError("Список локальных переменных пуст")

    return build_config_dict(
        remote_servers=remote_servers,
        local_server=local_server,
        polling_interval=polling,
        reconnect_interval=reconnect,
        auto_variables=False,
    )


def config_to_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Convert stored config to UI-friendly payload."""
    local_server = config.get("local_server", DEFAULT_LOCAL_SERVER)
    return {
        "remote_servers": config.get("remote_servers", []),
        "local_port": parse_local_port(local_server.get("url", DEFAULT_LOCAL_SERVER["url"])),
        "namespace_uri": local_server.get("namespace_uri", DEFAULT_LOCAL_SERVER["namespace_uri"]),
        "folder_name": local_server.get("folder_name", DEFAULT_LOCAL_SERVER["folder_name"]),
        "polling_interval": config.get("polling_interval", DEFAULT_POLLING_INTERVAL),
        "reconnect_interval": config.get("reconnect_interval", DEFAULT_RECONNECT_INTERVAL),
    }


def local_ip_hint() -> str:
    """Best-effort LAN IP for customer connection hints."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def namespace_uri_for_ip(ip: str) -> str:
    """Build namespace URI from the PC LAN IP."""
    return f"http://{ip.strip()}/opcua/gateway/"


def client_opc_url(ip: str, port: int | str) -> str:
    """Build opc.tcp URL for customer clients."""
    return f"opc.tcp://{ip.strip()}:{int(port)}"


def ip_from_namespace_uri(namespace_uri: str) -> str | None:
    """Extract host/IP from a namespace URI like http://192.168.1.98/opcua/gateway/."""
    uri = namespace_uri.strip()
    if not uri.lower().startswith("http://"):
        return None
    host = uri[7:].split("/", 1)[0].strip()
    return host or None


def host_from_opc_url(url: str) -> str | None:
    """Extract host/IP from opc.tcp://host:port."""
    trimmed = url.strip()
    if trimmed.lower().startswith("opc.tcp://"):
        trimmed = trimmed[10:]
    if not trimmed or ":" not in trimmed:
        return None
    host = trimmed.rsplit(":", 1)[0].strip()
    return host or None


def _should_auto_namespace(namespace_uri: str) -> bool:
    """Whether namespace URI should be replaced with detected LAN IP."""
    return namespace_uri.strip() in (
        "",
        DEFAULT_LOCAL_SERVER["namespace_uri"],
        "http://mycompany.com/opcua/gateway/",
    )


class LogBufferHandler(logging.Handler):
    """Capture log lines for the GUI log panel."""

    def __init__(self, buffer: deque[str]) -> None:
        super().__init__()
        self.buffer = buffer
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append(self.format(record))
        except Exception:
            self.handleError(record)


class GatewayService:
    """Run OpcUaGateway in a background thread with its own asyncio loop."""

    def __init__(self) -> None:
        self._gateway: OpcUaGateway | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._logs: deque[str] = deque(maxlen=1000)
        self._log_handler: LogBufferHandler | None = None
        self._running = False
        self._stopping = False
        self._user_stop_requested = False
        self._exit_callback: Callable[[bool], None] | None = None
        self._lock = threading.Lock()

    def set_exit_callback(self, callback: Callable[[bool], None] | None) -> None:
        """Called when gateway thread exits. Argument True = unexpected crash/stop."""
        self._exit_callback = callback

    @property
    def running(self) -> bool:
        return self._running

    @property
    def stopping(self) -> bool:
        return self._stopping

    def logs_since(self, offset: int) -> tuple[list[str], int]:
        items = list(self._logs)
        if offset < 0:
            offset = 0
        if offset >= len(items):
            return [], len(items)
        return items[offset:], len(items)

    def clear_logs(self) -> None:
        self._logs.clear()

    def start(self, config: dict[str, Any]) -> None:
        with self._lock:
            if self._running or self._stopping:
                raise RuntimeError("Шлюз уже запущен или останавливается")
            self._user_stop_requested = False
            self._running = True
            self._thread = threading.Thread(
                target=self._thread_main,
                args=(config,),
                name="opcua-gateway",
                daemon=True,
            )
            self._thread.start()

    def stop(self, done_callback: Callable[[], None] | None = None) -> None:
        """Request gateway stop without blocking the caller."""
        with self._lock:
            if not self._running:
                if done_callback is not None:
                    done_callback()
                return
            if self._stopping:
                return
            self._user_stop_requested = True
            self._stopping = True

        def _stop_worker() -> None:
            try:
                self._logs.append("[GUI] Остановка шлюза...")
                loop = self._loop
                gateway = self._gateway
                if loop is not None and gateway is not None:
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            gateway.stop(), loop
                        )
                        future.result(timeout=30)
                    except Exception as exc:
                        self._logs.append(f"[GUI] Ошибка остановки: {exc}")
                thread = self._thread
                if thread is not None and thread.is_alive():
                    thread.join(timeout=35)
                    if thread.is_alive():
                        self._logs.append(
                            "[GUI] Предупреждение: поток шлюза не завершился вовремя"
                        )
            finally:
                with self._lock:
                    self._stopping = False
                    self._running = False
                    self._gateway = None
                    self._thread = None
                    self._loop = None
                if done_callback is not None:
                    done_callback()

        threading.Thread(
            target=_stop_worker,
            name="opcua-gateway-stop",
            daemon=True,
        ).start()

    def get_status(self) -> dict[str, Any]:
        """Return gateway runtime status for diagram coloring (non-blocking)."""
        gateway = self._gateway
        running = self._running
        if gateway is not None and running:
            try:
                return gateway.get_status()
            except Exception:
                pass
        return {
            "running": running,
            "gateway_ok": False,
            "local_server_ok": False,
            "error": None,
            "plcs": {},
        }

    def _thread_main(self, config: dict[str, Any]) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        log_handler = LogBufferHandler(self._logs)
        self._log_handler = log_handler
        logging.getLogger().addHandler(log_handler)
        self._logs.append("[GUI] Запуск шлюза...")

        try:
            gateway = OpcUaGateway(config)
            self._gateway = gateway
            loop.run_until_complete(gateway.start())
        except Exception as exc:
            logger.error("Ошибка шлюза: %s", exc)
            self._logs.append(f"[GUI] Ошибка шлюза: {exc}")
        finally:
            self._logs.append("[GUI] Шлюз остановлен")
            unexpected = False
            with self._lock:
                unexpected = not self._user_stop_requested
                self._running = False
            root_logger = logging.getLogger()
            if self._log_handler is not None:
                root_logger.removeHandler(self._log_handler)
                self._log_handler = None
            self._gateway = None
            self._thread = None
            try:
                loop.close()
            finally:
                self._loop = None
            callback = self._exit_callback
            if callback is not None:
                callback(unexpected)


def _app_stylesheet() -> str:
    return f"""
        QMessageBox {{
            background-color: {COLORS['surface']};
        }}
        QMessageBox QLabel {{
            color: {COLORS['text']};
            font-family: "{FONT_UI}";
            font-size: 12px;
        }}
        QMessageBox QPushButton {{
            background: {COLORS['secondary_bg']};
            color: {COLORS['secondary_text']};
            border: 1px solid {COLORS['secondary_border']};
            border-radius: 8px;
            padding: 8px 15px;
            min-width: 72px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
        }}
        QMessageBox QPushButton:default {{
            background: {COLORS['accent']};
            color: {COLORS['header_text']};
            border: none;
        }}
    """


def _dialog_stylesheet() -> str:
    return f"""
        QDialog#settingsDialogRoot {{
            background: transparent;
            color: {COLORS['text']};
        }}
        QFrame#dialogPanel {{
            background-color: {COLORS['surface']};
            border: 1px solid #c8c8c8;
            border-radius: 8px;
        }}
        QWidget#dialogChrome {{
            background-color: {COLORS['surface']};
            border: none;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
        }}
        QLabel#dialogChromeTitle {{
            color: #333333;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            padding: 0;
            border: none;
        }}
        QLabel {{
            color: {COLORS['text']};
            background: transparent;
            font-family: "{FONT_UI}";
        }}
        QLineEdit {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
            padding: 9px 12px;
            min-height: 20px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QLineEdit:read-only {{
            background-color: {COLORS['surface2']};
            color: {COLORS['text']};
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus {{
            border: 1px solid {COLORS['secondary_border']};
            background-color: {COLORS['surface']};
            outline: none;
        }}
        QLineEdit:read-only:focus {{
            border: 1px solid {COLORS['secondary_border']};
            background-color: {COLORS['surface2']};
            outline: none;
        }}
        QTextEdit {{
            background-color: {COLORS['log_bg']};
            color: {COLORS['log_text']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
            font-family: "{FONT_MONO}";
            font-size: 11px;
            padding: 12px;
        }}
        QTextEdit:focus {{
            border: 1px solid {COLORS['border']};
            outline: none;
        }}
        QPushButton {{
            padding: 9px 16px;
            min-height: 20px;
            border-radius: 8px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
        }}
        QTreeWidget#opcTagTree,
        QTableWidget#opcSelectedTagsTable {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
            padding: 4px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            gridline-color: transparent;
        }}
        QTreeWidget#opcTagTree {{
            show-decoration-selected: 0;
        }}
        QTreeWidget#opcTagTree QHeaderView::section,
        QTableWidget#opcSelectedTagsTable QHeaderView::section {{
            background-color: {COLORS['surface2']};
            color: {COLORS['text_muted']};
            border: none;
            border-bottom: 1px solid {COLORS['border']};
            padding: 8px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QTreeWidget#opcTagTree::item,
        QTableWidget#opcSelectedTagsTable::item {{
            height: 24px;
            padding: 2px 4px;
        }}
        QTreeWidget#opcTagTree::item:selected,
        QTableWidget#opcSelectedTagsTable::item:selected {{
            background-color: #2563EB;
            color: #FFFFFF;
        }}
        QTableWidget {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
            gridline-color: {COLORS['border']};
            font-family: "{FONT_UI}";
            font-size: 12px;
        }}
        QHeaderView::section {{
            background-color: {COLORS['surface2']};
            color: {COLORS['text_muted']};
            border: none;
            border-bottom: 1px solid {COLORS['border']};
            padding: 8px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QSplitter::handle {{
            background-color: transparent;
        }}
        QSplitter::handle:horizontal {{
            width: 4px;
        }}
        QSplitter::handle:horizontal:hover,
        QSplitter::handle:horizontal:pressed {{
            background-color: transparent;
        }}
        QSplitter::handle:vertical {{
            height: 6px;
        }}
        QSplitter::handle:vertical:hover,
        QSplitter::handle:vertical:pressed {{
            background-color: transparent;
        }}
        QCheckBox {{
            color: {COLORS['text_muted']};
            font-family: "{FONT_UI}";
            font-size: 11px;
            spacing: 6px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
    """


def _dialog_btn_secondary(*, compact: bool = False) -> str:
    height = 36 if compact else 40
    hpad = 12 if compact else 14
    return f"""
        QPushButton {{
            background-color: {COLORS['secondary_bg']};
            color: {COLORS['secondary_text']};
            border: 1px solid {COLORS['secondary_border']};
            border-radius: 8px;
            padding: 0px {hpad}px;
            margin: 0px;
            min-height: {height}px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {COLORS['surface2']};
        }}
        QPushButton:pressed {{
            background-color: #e8e8e8;
        }}
        QPushButton:disabled {{
            color: {COLORS['text_muted']};
            background-color: {COLORS['surface2']};
        }}
    """


def _dialog_btn_inline() -> str:
    """Compact side button aligned with dialog text fields."""
    return _dialog_btn_secondary()


def _dialog_btn_primary(accent: str) -> str:
    hover_pressed = {
        COLORS["plc"]: ("#15803D", "#166534"),
        COLORS["gateway"]: ("#292524", "#1c1917"),
        COLORS["accent"]: ("#292524", "#1c1917"),
        COLORS["customer"]: ("#1D4ED8", "#1E40AF"),
        COLORS["danger"]: ("#991B1B", "#7F1D1D"),
    }
    hover, pressed = hover_pressed.get(accent, ("#292524", "#1c1917"))
    return f"""
        QPushButton {{
            background-color: {accent};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 0px 14px;
            margin: 0px;
            min-height: 40px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: {pressed};
        }}
        QPushButton:disabled {{
            background-color: {COLORS['surface2']};
            color: {COLORS['text_muted']};
        }}
    """


def _style_dialog_button(button: QPushButton, stylesheet: str) -> None:
    button.setStyleSheet(stylesheet)
    button.setCursor(Qt.CursorShape.PointingHandCursor)


def _prepare_dialog_layout(dialog: QDialog) -> QVBoxLayout:
    if isinstance(dialog, SettingsDialog):
        return dialog.content_layout()
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(8)
    layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
    return layout


def _add_dialog_buttons(
    layout: QVBoxLayout,
    on_cancel: Callable[[], None],
    on_apply: Callable[[], None],
    apply_text: str = "Применить",
    apply_color: str = COLORS["accent"],
) -> None:
    layout.addSpacing(16)
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)
    btn_row.addStretch()
    cancel_btn = QPushButton("Отмена")
    cancel_btn.setFixedWidth(104)
    _style_dialog_button(cancel_btn, _dialog_btn_secondary())
    cancel_btn.clicked.connect(on_cancel)
    apply_btn = QPushButton(apply_text)
    apply_btn.setFixedWidth(104)
    _style_dialog_button(apply_btn, _dialog_btn_primary(apply_color))
    apply_btn.clicked.connect(on_apply)
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(apply_btn)
    layout.addLayout(btn_row)


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: 500; padding-top: 2px;"
    )
    return label


def _make_field(initial: str = "", readonly: bool = False) -> QLineEdit:
    edit = QLineEdit(initial)
    edit.setFixedHeight(40)
    edit.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
    field_style = QStyleFactory.create("Fusion")
    if field_style is not None:
        edit.setStyle(field_style)
    if readonly:
        edit.setReadOnly(True)
    return edit


def _section_label(text: str, color: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-weight: 600; font-size: 12px; padding-top: 6px; padding-bottom: 2px;"
    )
    return label


def _column_field(label: str, initial: str = "") -> tuple[QWidget, QLineEdit]:
    wrap = QWidget()
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    column = QVBoxLayout(wrap)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)
    edit = _make_field(initial)
    column.addWidget(_field_label(label))
    column.addWidget(edit)
    return wrap, edit


def _add_field_row(layout: QVBoxLayout, fields: list[tuple[str, str]]) -> list[QLineEdit]:
    row = QHBoxLayout()
    row.setSpacing(10)
    edits: list[QLineEdit] = []
    for label, initial in fields:
        wrap, edit = _column_field(label, initial)
        row.addWidget(wrap, 1)
        edits.append(edit)
    layout.addLayout(row)
    return edits


def _add_grid_pair_section(
    grid: QGridLayout,
    row: int,
    title: str,
    title_color: str,
    left_label: str,
    left_value: str,
    right_label: str,
    right_value: str,
) -> tuple[int, QLineEdit, QLineEdit]:
    grid.addWidget(_section_label(title, title_color), row, 0, 1, 2)
    row += 1
    grid.addWidget(_field_label(left_label), row, 0)
    grid.addWidget(_field_label(right_label), row, 1)
    row += 1
    left_edit = _make_field(left_value)
    right_edit = _make_field(right_value)
    grid.addWidget(left_edit, row, 0)
    grid.addWidget(right_edit, row, 1)
    return row + 1, left_edit, right_edit


def _finalize_dialog_size(dialog: QDialog, min_width: int = 580, min_height: int = 480) -> None:
    dialog.adjustSize()
    dialog.resize(max(min_width, dialog.width()), max(min_height, dialog.height()))
    dialog.setMinimumSize(min_width, min_height)


def _message_box_stylesheet() -> str:
    return f"""
        QMessageBox {{
            background-color: {COLORS['surface']};
        }}
        QMessageBox QLabel {{
            color: {COLORS['text']};
            background-color: transparent;
            font-family: "{FONT_UI}";
            font-size: 12px;
            min-width: 320px;
        }}
        QMessageBox QPushButton {{
            background: {COLORS['secondary_bg']};
            color: {COLORS['secondary_text']};
            border: 1px solid {COLORS['secondary_border']};
            border-radius: 8px;
            padding: 8px 15px;
            min-width: 72px;
            font-family: "{FONT_UI}";
            font-size: 12px;
            font-weight: 600;
        }}
        QMessageBox QPushButton:default {{
            background: {COLORS['accent']};
            color: #FFFFFF;
            border: none;
        }}
    """


def _localize_message_box_buttons(box: QMessageBox) -> None:
    labels = {
        QMessageBox.StandardButton.Ok: "OK",
        QMessageBox.StandardButton.Yes: "Да",
        QMessageBox.StandardButton.No: "Нет",
        QMessageBox.StandardButton.Cancel: "Отмена",
        QMessageBox.StandardButton.Close: "Закрыть",
    }
    for role, label in labels.items():
        button = box.button(role)
        if button is not None:
            button.setText(label)


def _show_message(
    parent: QWidget,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
) -> QMessageBox.StandardButton:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    box.setStyleSheet(_message_box_stylesheet())
    _localize_message_box_buttons(box)
    return QMessageBox.StandardButton(box.exec())


def _show_confirm(
    parent: QWidget,
    *,
    chrome_title: str,
    message: str,
    detail: str = "",
    confirm_text: str = "Подтвердить",
    cancel_text: str = "Отмена",
    destructive: bool = False,
) -> bool:
    """Paper Ops confirmation dialog with aligned text and Russian buttons."""
    dialog = SettingsDialog(parent, chrome_title=chrome_title)
    dialog.setStyleSheet(_dialog_stylesheet())
    layout = dialog.content_layout()

    message_label = QLabel(message)
    message_label.setWordWrap(True)
    message_label.setStyleSheet(
        f"color: {COLORS['text']}; font-size: 13px; font-weight: 600; padding: 2px 0 6px 0;"
    )
    layout.addWidget(message_label)

    if detail:
        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; padding-bottom: 4px;"
        )
        layout.addWidget(detail_label)

    layout.addSpacing(10)
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)
    btn_row.addStretch()

    cancel_btn = QPushButton(cancel_text)
    cancel_btn.setFixedSize(104, 40)
    _style_dialog_button(cancel_btn, _dialog_btn_secondary())
    cancel_btn.clicked.connect(dialog.reject)

    confirm_btn = QPushButton(confirm_text)
    confirm_btn.setFixedSize(104, 40)
    accent = COLORS["danger"] if destructive else COLORS["accent"]
    _style_dialog_button(confirm_btn, _dialog_btn_primary(accent))
    confirm_btn.clicked.connect(dialog.accept)

    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(confirm_btn)
    layout.addLayout(btn_row)

    dialog.adjustSize()
    dialog.setMinimumWidth(420)
    dialog.resize(max(420, dialog.width()), max(160, dialog.height()))
    cancel_btn.setFocus()
    return dialog.exec() == QDialog.DialogCode.Accepted


def _styled_dialog(parent: QWidget, title: str, width: int = 460, height: int = 380) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumSize(width, height)
    dialog.resize(width, height)
    dialog.setStyleSheet(_dialog_stylesheet())
    return dialog


def _dialog_subtitle(layout: QVBoxLayout, subtitle: str) -> None:
    if not subtitle:
        return
    sub = QLabel(subtitle)
    sub.setWordWrap(True)
    sub.setStyleSheet(
        f"color: {COLORS['text_muted']}; font-size: 11px; line-height: 1.4; margin: 0; padding: 0 0 4px 0;"
    )
    layout.addWidget(sub)


def _dialog_header(layout: QVBoxLayout, title: str, subtitle: str = "", color: str = COLORS["text"]) -> None:
    header = QWidget()
    header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(2)

    title_label = QLabel(title)
    title_label.setObjectName("dialogTitle")
    title_label.setStyleSheet(
        f"font-family: '{FONT_UI}'; font-size: 15px; font-weight: 600; color: {color}; "
        f"margin: 0; padding: 0;"
    )
    header_layout.addWidget(title_label)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("dialogSubtitle")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; margin: 0; padding: 0;"
        )
        header_layout.addWidget(sub)

    layout.addWidget(header)
    layout.addSpacing(6)


def _labeled_entry(parent_layout: QVBoxLayout, label: str, initial: str = "", readonly: bool = False) -> QLineEdit:
    wrap, entry = _column_field(label, initial)
    if readonly:
        entry.setReadOnly(True)
    parent_layout.addWidget(wrap)
    return entry


def _labeled_entry_with_auto(
    parent_layout: QVBoxLayout,
    label: str,
    initial: str,
    on_auto: Callable[[], None],
) -> QLineEdit:
    wrap = QWidget()
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    column = QVBoxLayout(wrap)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)
    column.addWidget(_field_label(label))

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    entry = _make_field(initial)
    entry.setToolTip("Введите opc.tcp://IP:порт вручную или нажмите «Авто» для определения IP этого ПК.")
    auto_btn = QPushButton("Авто")
    auto_btn.setObjectName("autoIpButton")
    auto_btn.setFixedHeight(40)
    auto_btn.setMinimumWidth(78)
    auto_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    auto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _style_dialog_button(auto_btn, _dialog_btn_inline())
    auto_btn.setToolTip("Определить IP этого ПК в сети и подставить адрес")
    auto_btn.clicked.connect(on_auto)
    row.addWidget(entry, 1)
    row.addWidget(auto_btn, 0, Qt.AlignmentFlag.AlignVCenter)
    column.addLayout(row)
    parent_layout.addWidget(wrap)
    return entry


class _BrowseBridge(QObject):
    children_loaded = Signal(str, list)
    connected = Signal()
    failed = Signal(str)


class _LinkBridge(QObject):
    ok = Signal(str)
    failed = Signal(str)


class _TagVerifyBridge(QObject):
    done = Signal(dict)
    failed = Signal(str)


class _TagResolveBridge(QObject):
    done = Signal(list)
    failed = Signal(str)
    progress = Signal(int, str)


def _parse_tag_list_file(path: Path) -> list[tuple[str, str | None]]:
    """Parse txt: NodeId or tag name per line; optional local name after tab."""
    entries: list[tuple[str, str | None]] = []
    text = path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        local_override: str | None = None
        if "\t" in line:
            node_id, local_override = line.split("\t", 1)
            node_id = node_id.strip()
            local_override = local_override.strip() or None
        else:
            node_id = line
        if node_id:
            entries.append((node_id, local_override))
    return entries


def _sanitize_local_name(value: str) -> str:
    return re.sub(r"[^\w]+", "_", value).strip("_")


def _section_caption(text: str, color: str = COLORS["text_muted"]) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-size: 11px; font-weight: 600; padding-top: 8px; padding-bottom: 4px;"
    )
    return label


def _configure_opc_data_header(header: QHeaderView) -> None:
    """Shared header look for OPC tag tree and selected-tags table."""
    header.setStretchLastSection(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setHighlightSections(False)
    header.setFixedHeight(32)


def _labeled_url_with_poll(
    parent_layout: QVBoxLayout,
    label: str,
    initial: str,
    on_poll: Callable[[], None],
    on_link: Callable[[], None] | None = None,
) -> QLineEdit:
    wrap = QWidget()
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    column = QVBoxLayout(wrap)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)
    column.addWidget(_field_label(label))

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    entry = _make_field(initial)
    row.addWidget(entry, 1)
    if on_link is not None:
        link_btn = QPushButton("Связь")
        link_btn.setFixedHeight(40)
        link_btn.setMinimumWidth(78)
        link_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _style_dialog_button(link_btn, _dialog_btn_inline())
        link_btn.setToolTip("Проверить связь с контроллером")
        link_btn.clicked.connect(on_link)
        row.addWidget(link_btn, 0, Qt.AlignmentFlag.AlignVCenter)
    poll_btn = QPushButton("Опрос")
    poll_btn.setFixedHeight(40)
    poll_btn.setMinimumWidth(88)
    poll_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    _style_dialog_button(poll_btn, _dialog_btn_inline())
    poll_btn.setToolTip("Подключиться к контроллеру и загрузить список тегов")
    poll_btn.clicked.connect(on_poll)
    row.addWidget(poll_btn, 0, Qt.AlignmentFlag.AlignVCenter)
    column.addLayout(row)
    parent_layout.addWidget(wrap)
    return entry


class PlcSettingsDialog(SettingsDialog):
    """Settings dialog for one OWEN210 PLC with OPC UA tag browsing."""

    _ROLE_NODE_ID = Qt.ItemDataRole.UserRole
    _ROLE_LOADED = Qt.ItemDataRole.UserRole + 1
    _ROLE_NODE_CLASS = Qt.ItemDataRole.UserRole + 2
    _ROLE_BROWSE_NAME = Qt.ItemDataRole.UserRole + 3
    _ROLE_EMPTY = "__empty__"

    _COL_PLC_NAME = 0
    _COL_LOCAL_NAME = 1
    _COL_NODE_ID = 2
    _COL_TYPE = 3
    _COL_STATUS = 4

    def __init__(
        self,
        parent: QWidget,
        index: int,
        server: dict[str, Any],
        on_apply: Callable[[int, dict[str, Any]], None],
    ) -> None:
        super().__init__(parent, chrome_title=plc_display_name(server, index))
        self.index = index
        self.on_apply = on_apply
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._pending_file_locals: dict[str, str] = {}
        self._tag_resolve_cancel = threading.Event()
        self._tag_file_progress: QProgressDialog | None = None
        self._browse_bridge = _BrowseBridge()
        self._browse_bridge.children_loaded.connect(self._on_browse_children)
        self._browse_bridge.connected.connect(self._on_browse_connected)
        self._browse_bridge.failed.connect(self._on_browse_failed)
        self._link_bridge = _LinkBridge()
        self._link_bridge.ok.connect(self._on_link_ok)
        self._link_bridge.failed.connect(self._on_link_failed)
        self._tag_verify_bridge = _TagVerifyBridge()
        self._tag_verify_bridge.done.connect(self._on_tags_verified)
        self._tag_verify_bridge.failed.connect(self._on_tags_verify_failed)
        self._tag_resolve_bridge = _TagResolveBridge()
        self._tag_resolve_bridge.done.connect(self._on_tags_file_resolved)
        self._tag_resolve_bridge.failed.connect(self._on_tags_file_resolve_failed)
        self._tag_resolve_bridge.progress.connect(self._on_tags_file_resolve_progress)
        self._browser = OpcUaBrowserSession(
            on_children=lambda parent_id, nodes: self._browse_bridge.children_loaded.emit(parent_id, nodes),
            on_connected=lambda: self._browse_bridge.connected.emit(),
            on_error=lambda message: self._browse_bridge.failed.emit(message),
        )

        self.setStyleSheet(_dialog_stylesheet())

        layout = _prepare_dialog_layout(self)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        name_wrap, self.name_edit = _column_field("Имя ПЛК", server.get("name", ""))
        self.name_edit.textChanged.connect(self._update_dialog_title)
        top_row.addWidget(name_wrap, 1)
        url_wrap = QWidget()
        url_col = QVBoxLayout(url_wrap)
        url_col.setContentsMargins(0, 0, 0, 0)
        url_col.setSpacing(4)
        self.url_edit = _labeled_url_with_poll(
            url_col,
            "URL (opc.tcp://…)",
            server.get("url", ""),
            self._start_browse,
            self._test_connection,
        )
        top_row.addWidget(url_wrap, 2)
        layout.addLayout(top_row)

        self.status_label = QLabel("Нажмите «Связь» для проверки или «Опрос» для загрузки тегов")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; padding: 2px 0 6px 0;"
        )
        layout.addWidget(self.status_label)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(4)
        main_splitter.setOpaqueResize(True)
        main_splitter.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        browse_panel = QWidget()
        browse_layout = QVBoxLayout(browse_panel)
        browse_layout.setContentsMargins(0, 0, 8, 0)
        browse_layout.setSpacing(6)
        browse_layout.addWidget(_section_caption("Теги на контроллере", COLORS["plc"]))

        self.tag_tree = QTreeWidget()
        self.tag_tree.setObjectName("opcTagTree")
        self.tag_tree.setHeaderLabels(["Имя", "NodeId", "Тип"])
        self.tag_tree.setIndentation(22)
        self.tag_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tree_header = self.tag_tree.header()
        _configure_opc_data_header(tree_header)
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tag_tree.setColumnWidth(0, 320)
        self.tag_tree.setColumnWidth(2, 80)
        self.tag_tree.setMinimumHeight(280)
        self.tag_tree.setRootIsDecorated(True)
        self.tag_tree.setAlternatingRowColors(True)
        self.tag_tree.setUniformRowHeights(True)
        self.tag_tree.setAnimated(True)
        self.tag_tree.setExpandsOnDoubleClick(False)
        self.tag_tree.setItemsExpandable(True)
        self.tag_tree.setAllColumnsShowFocus(True)
        tree_style = QStyleFactory.create("Windows")
        if tree_style is not None:
            self.tag_tree.setStyle(tree_style)
        self.tag_tree.itemExpanded.connect(self._on_tree_expanded)
        self.tag_tree.itemCollapsed.connect(self._on_tree_collapsed)
        self.tag_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        browse_layout.addWidget(self.tag_tree, 1)

        browse_actions = QHBoxLayout()
        browse_actions.addStretch()
        self.add_tag_btn = QPushButton("Добавить →")
        _style_dialog_button(self.add_tag_btn, _dialog_btn_secondary(compact=True))
        self.add_tag_btn.setEnabled(False)
        self.add_tag_btn.clicked.connect(self._add_selected_tag)
        browse_actions.addWidget(self.add_tag_btn)
        browse_layout.addLayout(browse_actions)

        selected_panel = QWidget()
        selected_layout = QVBoxLayout(selected_panel)
        selected_layout.setContentsMargins(8, 0, 0, 0)
        selected_layout.setSpacing(6)

        selected_header = QHBoxLayout()
        selected_header.addWidget(_section_caption("Выбранные теги"))
        selected_header.addStretch()
        self.selected_count_label = QLabel("0 тегов")
        self.selected_count_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; padding-top: 8px;"
        )
        selected_header.addWidget(self.selected_count_label)
        selected_layout.addLayout(selected_header)

        self.selected_table = QTableWidget(0, 5)
        self.selected_table.setObjectName("opcSelectedTagsTable")
        self.selected_table.setHorizontalHeaderLabels(
            ["Имя на ПЛК", "Локальное имя", "NodeId", "Тип", "Статус"]
        )
        self.selected_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header = self.selected_table.horizontalHeader()
        _configure_opc_data_header(header)
        header.setSectionResizeMode(self._COL_PLC_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self._COL_LOCAL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self._COL_NODE_ID, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._COL_TYPE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self._COL_STATUS, QHeaderView.ResizeMode.Fixed)
        self.selected_table.setColumnWidth(self._COL_PLC_NAME, 300)
        self.selected_table.setColumnWidth(self._COL_LOCAL_NAME, 280)
        self.selected_table.setColumnWidth(self._COL_TYPE, 80)
        self.selected_table.setColumnWidth(self._COL_STATUS, 100)
        self.selected_table.setCornerButtonEnabled(False)
        self.selected_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.selected_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.selected_table.setMinimumHeight(280)
        self.selected_table.setShowGrid(False)
        self.selected_table.setAlternatingRowColors(True)
        self.selected_table.verticalHeader().setVisible(False)
        self.selected_table.verticalHeader().setDefaultSectionSize(28)
        table_style = QStyleFactory.create("Windows")
        if table_style is not None:
            self.selected_table.setStyle(table_style)
        selected_layout.addWidget(self.selected_table, 1)

        selected_actions = QHBoxLayout()
        selected_actions.addStretch()
        self.load_tags_file_btn = QPushButton("Загрузить теги из файла")
        _style_dialog_button(self.load_tags_file_btn, _dialog_btn_secondary(compact=True))
        self.load_tags_file_btn.clicked.connect(self._load_tags_from_file)
        self.verify_tags_btn = QPushButton("Проверить")
        _style_dialog_button(self.verify_tags_btn, _dialog_btn_secondary(compact=True))
        self.verify_tags_btn.clicked.connect(self._verify_selected_tags)
        clear_btn = QPushButton("Очистить")
        _style_dialog_button(clear_btn, _dialog_btn_secondary(compact=True))
        clear_btn.clicked.connect(self._clear_selected_tags)
        remove_btn = QPushButton("Удалить")
        _style_dialog_button(remove_btn, _dialog_btn_secondary(compact=True))
        remove_btn.clicked.connect(self._remove_selected_tag)
        selected_actions.addWidget(self.load_tags_file_btn)
        selected_actions.addWidget(self.verify_tags_btn)
        selected_actions.addWidget(clear_btn)
        selected_actions.addWidget(remove_btn)
        selected_layout.addLayout(selected_actions)

        main_splitter.addWidget(browse_panel)
        main_splitter.addWidget(selected_panel)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([680, 680])
        layout.addWidget(main_splitter, 1)

        for node in server.get("nodes", []):
            local_id = str(node.get("local_node_id", ""))
            self._append_selected_tag(
                str(node.get("node_id", "")),
                local_id.rsplit("_", 1)[-1] if local_id else "",
                local_id,
                str(node.get("node_class", "Variable")),
            )

        _add_dialog_buttons(layout, self.reject, self._apply, apply_color=COLORS["plc"])
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        max_h = int(avail.height() * 0.9) if avail else 820
        max_w = int(avail.width() * 0.94) if avail else 1720
        dialog_w = min(1720, max_w)
        dialog_h = min(820, max_h)
        _finalize_dialog_size(self, min_width=min(1680, max_w), min_height=min(720, max_h))
        self.setMaximumHeight(max_h)
        self.resize(dialog_w, dialog_h)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._browser.close()
        super().closeEvent(event)

    def reject(self) -> None:
        self._browser.close()
        super().reject()

    def _update_dialog_title(self, text: str) -> None:
        self.set_chrome_title(text.strip() or f"ПЛК #{self.index + 1}")

    def _set_status(self, text: str, *, error: bool = False, success: bool = False) -> None:
        if error:
            color = COLORS["danger"]
        elif success:
            color = COLORS["success"]
        else:
            color = COLORS["text_muted"]
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 2px 0 4px 0;"
        )
        self.status_label.setText(text)

    def _test_connection(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", "Укажите URL контроллера")
            return
        self._set_status("Проверка связи с контроллером…")
        test_opcua_connection_async(
            url,
            on_ok=lambda message: self._link_bridge.ok.emit(message),
            on_error=lambda message: self._link_bridge.failed.emit(message),
        )

    def _on_link_ok(self, message: str) -> None:
        self._set_status(f"Связь установлена: {message}", success=True)

    def _on_link_failed(self, message: str) -> None:
        self._set_status(f"Нет связи: {message}", error=True)

    def _start_browse(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", "Укажите URL контроллера")
            return
        self.tag_tree.clear()
        self._tree_items.clear()
        self.add_tag_btn.setEnabled(False)
        self._set_status("Подключение к контроллеру…")
        self._browser.connect(url)

    def _create_tree_item(self, node: dict[str, Any]) -> QTreeWidgetItem:
        display = node.get("display_name") or node.get("browse_name") or node.get("node_id", "")
        item = QTreeWidgetItem(
            [
                str(display),
                str(node.get("node_id", "")),
                str(node.get("node_class", "")),
            ]
        )
        item.setData(0, self._ROLE_NODE_ID, node.get("node_id", ""))
        item.setData(0, self._ROLE_NODE_CLASS, node.get("node_class", ""))
        item.setData(0, self._ROLE_BROWSE_NAME, node.get("browse_name", ""))
        item.setData(0, self._ROLE_LOADED, False)
        if node.get("has_children") and node.get("node_class") != "Variable":
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        self._sync_tree_branch_label(item)
        return item

    def _on_browse_connected(self) -> None:
        self._set_status("Подключено. Раскройте папки и выберите теги типа Variable.")
        self.add_tag_btn.setEnabled(True)

    def _on_browse_failed(self, message: str) -> None:
        self._set_status(f"Ошибка: {message}", error=True)
        self.add_tag_btn.setEnabled(False)

    def _on_browse_children(self, parent_id: str, nodes: list[dict[str, Any]]) -> None:
        if parent_id not in self._tree_items:
            self.tag_tree.clear()
            self._tree_items.clear()
            root = self.tag_tree.invisibleRootItem()
            parent_item = root
        else:
            parent_item = self._tree_items[parent_id]
            while parent_item.childCount() > 0:
                child = parent_item.child(0)
                child_id = child.data(0, self._ROLE_NODE_ID)
                if isinstance(child_id, str):
                    self._tree_items.pop(child_id, None)
                parent_item.removeChild(child)
            parent_item.setData(0, self._ROLE_LOADED, True)
            if not nodes:
                parent_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
                folder_name = str(parent_item.data(0, self._ROLE_BROWSE_NAME) or parent_item.text(0))
                folder_name = folder_name.lstrip("▸ ").lstrip("▾ ").strip()
                parent_item.setText(0, folder_name)
                self._add_empty_folder_placeholder(parent_item)

        for node in nodes:
            item = self._create_tree_item(node)
            parent_item.addChild(item)
            node_id = str(node.get("node_id", ""))
            if node_id:
                self._tree_items[node_id] = item

        if parent_id not in self._tree_items and self.tag_tree.topLevelItemCount() == 0:
            self._set_status("На контроллере не найдено узлов для отображения", error=True)
        elif parent_id not in self._tree_items:
            self._set_status("Подключено. Раскройте папки и выберите теги типа Variable.")
        elif not nodes:
            folder_item = self._tree_items.get(parent_id)
            folder_name = ""
            if folder_item is not None:
                folder_name = str(folder_item.data(0, self._ROLE_BROWSE_NAME) or folder_item.text(0)).strip()
            self._set_status(
                f"«{folder_name or 'Папка'}» — пустая папка (тегов нет)",
            )
        else:
            self._set_status(f"Загружено узлов: {len(nodes)}. Выберите Variable или раскройте папку.")

    def _add_empty_folder_placeholder(self, parent_item: QTreeWidgetItem) -> None:
        """Show a visible empty state instead of a blank expanded folder."""
        empty = QTreeWidgetItem(["(пусто)", "—", ""])
        empty.setData(0, self._ROLE_NODE_ID, self._ROLE_EMPTY)
        empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
        muted = QColor(COLORS["text_muted"])
        for column in range(3):
            empty.setForeground(column, muted)
        parent_item.addChild(empty)
        parent_item.setExpanded(True)

    def _update_selected_count(self) -> None:
        count = self.selected_table.rowCount()
        word = "тег" if count % 10 == 1 and count % 100 != 11 else "тегов"
        if count in {2, 3, 4} or (count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}):
            word = "тега"
        self.selected_count_label.setText(f"{count} {word}")

    def _sync_tree_branch_label(self, item: QTreeWidgetItem) -> None:
        """Prefix folder rows with expand/collapse hint for readability."""
        if item.childIndicatorPolicy() == QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator:
            return
        base_name = str(item.data(0, self._ROLE_BROWSE_NAME) or item.text(0)).lstrip("▸ ").lstrip("▾ ")
        if item.isExpanded():
            item.setText(0, f"▾ {base_name}")
        else:
            item.setText(0, f"▸ {base_name}")

    def _on_tree_collapsed(self, item: QTreeWidgetItem) -> None:
        self._sync_tree_branch_label(item)

    def _on_tree_expanded(self, item: QTreeWidgetItem) -> None:
        if item.data(0, self._ROLE_NODE_ID) == self._ROLE_EMPTY:
            return
        self._sync_tree_branch_label(item)
        if item.data(0, self._ROLE_LOADED):
            return
        node_id = item.data(0, self._ROLE_NODE_ID)
        if not isinstance(node_id, str) or not node_id:
            return
        if not self._browser.active:
            return
        self._set_status(f"Загрузка: {item.text(0).lstrip('▸ ').lstrip('▾ ')}…")
        self._browser.browse(node_id)

    def _on_tree_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, self._ROLE_NODE_ID) == self._ROLE_EMPTY:
            return
        node_class = str(item.data(0, self._ROLE_NODE_CLASS) or "")
        if node_class == "Variable":
            self._add_selected_tag()
            return
        if item.childIndicatorPolicy() != QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator:
            item.setExpanded(not item.isExpanded())
            self._set_status("Раскройте папку и выберите тег типа Variable")

    def _append_selected_tag(
        self,
        node_id: str,
        browse_name: str,
        local_name: str,
        node_type: str = "Variable",
    ) -> None:
        node_id = node_id.strip()
        local_name = local_name.strip()
        browse_name = browse_name.strip()
        node_type = node_type.strip() or "Variable"
        if not node_id or not local_name:
            return
        for row in range(self.selected_table.rowCount()):
            existing = self.selected_table.item(row, self._COL_NODE_ID)
            if existing is not None and existing.text() == node_id:
                return
        row = self.selected_table.rowCount()
        self.selected_table.insertRow(row)
        values = [browse_name, local_name, node_id, node_type, "—"]
        for col, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if col != self._COL_LOCAL_NAME:
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.selected_table.setItem(row, col, cell)
        self._update_selected_count()

    def _set_tag_row_status(self, row: int, status: str) -> None:
        cell = self.selected_table.item(row, self._COL_STATUS)
        if cell is None:
            cell = QTableWidgetItem(status)
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.selected_table.setItem(row, self._COL_STATUS, cell)
        else:
            cell.setText(status)
        if status == "Связь":
            cell.setForeground(QColor(COLORS["success"]))
        elif status == "Нет связи":
            cell.setForeground(QColor(COLORS["danger"]))
        else:
            cell.setForeground(QColor(COLORS["text_muted"]))

    def _verify_selected_tags(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", "Укажите URL контроллера")
            return
        node_ids: list[str] = []
        for row in range(self.selected_table.rowCount()):
            node_item = self.selected_table.item(row, self._COL_NODE_ID)
            if node_item is None:
                continue
            node_id = node_item.text().strip()
            if node_id:
                node_ids.append(node_id)
                self._set_tag_row_status(row, "Проверка…")
        if not node_ids:
            _show_message(self, QMessageBox.Icon.Information, "Проверка", "Нет тегов для проверки")
            return
        self.verify_tags_btn.setEnabled(False)
        self._set_status("Проверка связи с выбранными тегами…")
        verify_opcua_tags_async(
            url,
            node_ids,
            on_done=lambda results: self._tag_verify_bridge.done.emit(results),
            on_error=lambda message: self._tag_verify_bridge.failed.emit(message),
        )

    def _on_tags_verified(self, results: dict) -> None:
        self.verify_tags_btn.setEnabled(True)
        ok_count = 0
        for row in range(self.selected_table.rowCount()):
            node_item = self.selected_table.item(row, self._COL_NODE_ID)
            if node_item is None:
                continue
            node_id = node_item.text().strip()
            status = results.get(node_id, "Нет связи")
            self._set_tag_row_status(row, status)
            if status == "Связь":
                ok_count += 1
        total = len(results)
        self._set_status(
            f"Проверено: {ok_count} из {total} со связью",
            success=ok_count == total and total > 0,
            error=ok_count == 0,
        )

    def _on_tags_verify_failed(self, message: str) -> None:
        self.verify_tags_btn.setEnabled(True)
        self._set_status(f"Ошибка проверки: {message}", error=True)
        for row in range(self.selected_table.rowCount()):
            cell = self.selected_table.item(row, self._COL_STATUS)
            if cell is not None and cell.text() == "Проверка…":
                self._set_tag_row_status(row, "Нет связи")

    def _load_tags_from_file(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", "Укажите URL контроллера")
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Загрузить теги из файла",
            "",
            "Текстовые файлы (*.txt);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            entries = _parse_tag_list_file(Path(path))
        except OSError as exc:
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", f"Не удалось прочитать файл:\n{exc}")
            return
        if not entries:
            _show_message(
                self,
                QMessageBox.Icon.Information,
                "Загрузка",
                "В файле не найдено тегов.\n\n"
                "Формат: одно имя или NodeId на строку, например:\n"
                "OUT_TIME_DAY\n"
                "ns=2;i=1001",
            )
            return
        self._pending_file_locals = {query: local for query, local in entries if local}
        self._tag_resolve_cancel.clear()
        self.load_tags_file_btn.setEnabled(False)
        self.verify_tags_btn.setEnabled(False)
        self._set_status(f"Поиск и загрузка {len(entries)} тегов с контроллера…")
        self._open_tag_file_progress(len(entries))
        resolve_tag_list_entries_async(
            url,
            entries,
            on_done=lambda resolved: self._tag_resolve_bridge.done.emit(resolved),
            on_error=lambda message: self._tag_resolve_bridge.failed.emit(message),
            on_progress=lambda percent, message: self._tag_resolve_bridge.progress.emit(percent, message),
            cancel_check=self._tag_resolve_cancel.is_set,
        )

    def _open_tag_file_progress(self, total: int) -> None:
        self._close_tag_file_progress()
        dialog = QProgressDialog(
            f"Подключение к контроллеру… (тегов в файле: {total})",
            "Отмена",
            0,
            100,
            self,
        )
        dialog.setWindowTitle("Загрузка тегов из файла")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        dialog.canceled.connect(self._cancel_tag_file_resolve)
        self._tag_file_progress = dialog
        dialog.show()

    def _close_tag_file_progress(self) -> None:
        dialog = self._tag_file_progress
        self._tag_file_progress = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()

    def _cancel_tag_file_resolve(self) -> None:
        self._tag_resolve_cancel.set()
        self._set_status("Отмена загрузки тегов…")

    def _on_tags_file_resolve_progress(self, percent: int, message: str) -> None:
        dialog = self._tag_file_progress
        if dialog is None:
            return
        dialog.setValue(max(0, min(100, percent)))
        dialog.setLabelText(message)

    def _on_tags_file_resolved(self, resolved: list[dict[str, Any]]) -> None:
        self._close_tag_file_progress()
        self.load_tags_file_btn.setEnabled(True)
        self.verify_tags_btn.setEnabled(True)
        plc_name = self.name_edit.text().strip() or f"BHK1_PLC{self.index + 1}"
        pending_locals: dict[str, str] = self._pending_file_locals
        added = 0
        skipped = 0
        for entry in resolved:
            if not entry.get("ok"):
                skipped += 1
                continue
            node_id = str(entry.get("node_id", "")).strip()
            query = str(entry.get("query", "")).strip()
            browse_name = str(entry.get("browse_name") or entry.get("display_name") or query or node_id).strip()
            node_type = str(entry.get("node_class") or "Variable").strip()
            local_name = (
                pending_locals.get(query)
                or pending_locals.get(node_id)
                or f"{plc_name}_{_sanitize_local_name(browse_name)}"
            )
            before = self.selected_table.rowCount()
            self._append_selected_tag(node_id, browse_name, local_name, node_type)
            if self.selected_table.rowCount() > before:
                added += 1
        self._pending_file_locals = {}
        if added == 0:
            self._set_status("Не удалось добавить теги из файла", error=True)
            _show_message(
                self,
                QMessageBox.Icon.Warning,
                "Загрузка",
                "Ни один тег из файла не найден на контроллере.\n\n"
                "Укажите имя переменной (OUT_TIME_DAY) или NodeId (ns=2;i=1001).",
            )
            return
        msg = f"Добавлено тегов: {added}"
        if skipped:
            msg += f", не найдено: {skipped}"
        self._set_status(msg, success=True)

    def _on_tags_file_resolve_failed(self, message: str) -> None:
        self._close_tag_file_progress()
        self.load_tags_file_btn.setEnabled(True)
        self.verify_tags_btn.setEnabled(True)
        self._pending_file_locals = {}
        cancelled = "отменена" in message.lower()
        if cancelled:
            self._set_status(message or "Загрузка отменена", error=False)
            return
        detail = message.strip() or "Неизвестная ошибка"
        self._set_status(f"Ошибка загрузки из файла: {detail}", error=True)
        _show_message(
            self,
            QMessageBox.Icon.Warning,
            "Загрузка тегов",
            f"{detail}\n\n"
            "Совет: укажите NodeId (ns=2;i=1001) вместо имени — загрузка будет быстрее.",
        )

    def _add_selected_tag(self) -> None:
        item = self.tag_tree.currentItem()
        if item is None or item.data(0, self._ROLE_NODE_ID) == self._ROLE_EMPTY:
            return
        node_class = str(item.data(0, self._ROLE_NODE_CLASS) or "")
        if node_class != "Variable":
            self._set_status("Выберите тег типа Variable (переменную), а не папку")
            return
        node_id = str(item.data(0, self._ROLE_NODE_ID) or item.text(1))
        browse_name = str(item.data(0, self._ROLE_BROWSE_NAME) or item.text(0)).lstrip("▸ ").lstrip("▾ ").strip()
        node_type = str(item.data(0, self._ROLE_NODE_CLASS) or item.text(2) or "Variable")
        plc_name = self.name_edit.text().strip() or f"BHK1_PLC{self.index + 1}"
        local_name = f"{plc_name}_{_sanitize_local_name(browse_name)}"
        self._append_selected_tag(node_id, browse_name, local_name, node_type)

    def _remove_selected_tag(self) -> None:
        rows = sorted({index.row() for index in self.selected_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.selected_table.removeRow(row)
        self._update_selected_count()

    def _clear_selected_tags(self) -> None:
        count = self.selected_table.rowCount()
        if count == 0:
            return
        if not _show_confirm(
            self,
            chrome_title="Очистить список",
            message="Удалить все выбранные теги?",
            detail=f"В таблице {count} тег(ов). Список станет пустым.",
            confirm_text="Очистить",
            destructive=True,
        ):
            return
        self.selected_table.setRowCount(0)
        self._update_selected_count()

    def _collect_nodes(self) -> list[dict[str, str]]:
        nodes: list[dict[str, str]] = []
        for row in range(self.selected_table.rowCount()):
            node_id_item = self.selected_table.item(row, self._COL_NODE_ID)
            local_item = self.selected_table.item(row, self._COL_LOCAL_NAME)
            if node_id_item is None or local_item is None:
                continue
            node_id = node_id_item.text().strip()
            local_id = local_item.text().strip()
            if node_id and local_id:
                nodes.append({"node_id": node_id, "local_node_id": local_id})
        return nodes

    def _apply(self) -> None:
        if not self.url_edit.text().strip():
            _show_message(self, QMessageBox.Icon.Critical, "Ошибка", "Укажите URL ПЛК")
            return
        nodes = self._collect_nodes()
        if not nodes:
            _show_message(
                self,
                QMessageBox.Icon.Critical,
                "Ошибка",
                "Добавьте хотя бы один тег из списка контроллера",
            )
            return

        server = {
            "name": self.name_edit.text().strip() or f"ПЛК #{self.index + 1}",
            "url": self.url_edit.text().strip(),
            "nodes": nodes,
        }
        self._browser.close()
        self.on_apply(self.index, server)
        self.accept()


class GatewaySettingsDialog(SettingsDialog):
    """Settings dialog for the local OPC UA gateway server."""

    def __init__(
        self,
        parent: QWidget,
        payload: dict[str, Any],
        on_apply: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(parent, chrome_title="Шлюз")
        self.on_apply = on_apply
        self.setStyleSheet(_dialog_stylesheet())

        layout = _prepare_dialog_layout(self)

        port = int(payload.get("local_port", 4841) or 4841)
        self.port_edit = _labeled_entry(layout, "Порт локального сервера", str(port))
        namespace_uri = str(payload.get("namespace_uri", DEFAULT_LOCAL_SERVER["namespace_uri"])).strip()
        if namespace_uri == "http://mycompany.com/opcua/gateway/":
            namespace_uri = DEFAULT_LOCAL_SERVER["namespace_uri"]
        initial_ip = ip_from_namespace_uri(namespace_uri) or local_ip_hint()
        self.client_url_edit = _labeled_entry_with_auto(
            layout,
            "IP-адрес для клиента (opc.tcp)",
            client_opc_url(initial_ip, port),
            lambda: self._auto_client_ip(update_namespace=True),
        )
        self.namespace_edit = _labeled_entry(layout, "URI пространства имён", namespace_uri)
        if _should_auto_namespace(namespace_uri):
            self._auto_client_ip(update_namespace=True)

        self.folder_edit = _labeled_entry(layout, "Имя папки переменных", payload.get("folder_name", "GatewayData"))
        self.polling_edit = _labeled_entry(
            layout, "Интервал опроса (сек)", str(payload.get("polling_interval", DEFAULT_POLLING_INTERVAL))
        )
        self.reconnect_edit = _labeled_entry(
            layout, "Интервал переподключения (сек)", str(payload.get("reconnect_interval", DEFAULT_RECONNECT_INTERVAL))
        )

        _add_dialog_buttons(layout, self.reject, self._apply, apply_color=COLORS["gateway"])
        _finalize_dialog_size(self, min_width=580, min_height=540)

    def _current_port(self) -> int:
        try:
            return int(self.port_edit.text().strip() or 4841)
        except ValueError:
            return 4841

    def _auto_client_ip(self, update_namespace: bool = True) -> None:
        ip = local_ip_hint()
        port = self._current_port()
        self.client_url_edit.setText(client_opc_url(ip, port))
        if update_namespace:
            self.namespace_edit.setText(namespace_uri_for_ip(ip))

    def _apply(self) -> None:
        try:
            port = int(self.port_edit.text().strip() or 4841)
            polling = float(self.polling_edit.text().strip())
            reconnect = float(self.reconnect_edit.text().strip())
        except ValueError:
            QMessageBox.critical(self, "Ошибка", "Порт и интервалы должны быть числами")
            return
        if port < 1 or port > 65535:
            QMessageBox.critical(self, "Ошибка", "Порт: от 1 до 65535")
            return
        if polling <= 0 or reconnect <= 0:
            QMessageBox.critical(self, "Ошибка", "Интервалы должны быть больше 0")
            return

        namespace_uri = self.namespace_edit.text().strip()
        client_host = host_from_opc_url(self.client_url_edit.text())
        if client_host and client_host != "0.0.0.0":
            namespace_uri = namespace_uri_for_ip(client_host)

        changes = {
            "local_port": port,
            "namespace_uri": namespace_uri,
            "folder_name": self.folder_edit.text().strip() or "GatewayData",
            "polling_interval": polling,
            "reconnect_interval": reconnect,
        }
        self.on_apply(changes)
        self.accept()


class CustomerInfoDialog(SettingsDialog):
    """Read-only connection info for the customer OPC UA client."""

    def __init__(self, parent: QWidget, payload: dict[str, Any]) -> None:
        super().__init__(parent, chrome_title="Клиент заказчика")
        port = int(payload.get("local_port", 4841))
        folder = payload.get("folder_name", "GatewayData")
        polling = payload.get("polling_interval", DEFAULT_POLLING_INTERVAL)
        ip = local_ip_hint()

        self.setStyleSheet(_dialog_stylesheet())

        layout = _prepare_dialog_layout(self)
        _dialog_subtitle(layout, "Информация для подключения через UaExpert или SCADA")

        info = (
            f"Адрес подключения:\n"
            f"  opc.tcp://{ip}:{port}\n"
            f"  opc.tcp://127.0.0.1:{port}  (на этом ПК)\n\n"
            f"UaExpert — пошагово:\n"
            f"  1. Сервер → Добавить → opc.tcp://<IP_ПК_с_шлюзом>:{port}\n"
            f"  2. Безопасность: Anonymous → Подключиться\n"
            f"  3. Объекты → {folder}\n"
            f"  4. Значения обновляются каждые ~{polling} с\n\n"
            f"Убедитесь, что шлюз запущен и порт {port} открыт в брандмауэре Windows."
        )

        text = QTextEdit()
        text.setPlainText(info)
        text.setReadOnly(True)
        text.setMinimumHeight(220)
        layout.addWidget(text)

        layout.addSpacing(8)
        close_btn = QPushButton("Закрыть")
        _style_dialog_button(close_btn, _dialog_btn_primary(COLORS["customer"]))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        _finalize_dialog_size(self, min_width=560, min_height=440)


class LogJournalDialog(SettingsDialog):
    """Separate window for gateway event log."""

    def __init__(self, parent: "GatewayApp") -> None:
        super().__init__(parent, chrome_title="Журнал событий")
        self._app = parent
        self.setStyleSheet(
            _dialog_stylesheet()
            + f"""
            QTextEdit#logJournalView {{
                background-color: {COLORS['log_bg']};
                color: {COLORS['log_text']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                font-family: "{FONT_MONO}";
                font-size: 11px;
                padding: 14px 16px;
            }}
            QLabel#logJournalHint {{
                color: {COLORS['text_muted']};
                font-size: 11px;
                padding-bottom: 6px;
            }}
            QLabel#logJournalCount {{
                color: {COLORS['text_muted']};
                font-size: 11px;
                padding-bottom: 8px;
            }}
            """
        )

        layout = _prepare_dialog_layout(self)
        log_path = getattr(parent, "_log_file_path", None)
        file_hint = f"\nФайл на диске: {log_path}" if log_path else ""
        _dialog_subtitle(
            layout,
            f"События шлюза и приложения · обновляется автоматически{file_hint}",
        )

        self._count_label = QLabel("0 записей")
        self._count_label.setObjectName("logJournalCount")
        layout.addWidget(self._count_label)

        self._log_view = QTextEdit()
        self._log_view.setObjectName("logJournalView")
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText(
            "Журнал пуст.\n\nЗапустите шлюз или выполните действия в приложении — записи появятся здесь."
        )
        self._log_view.setMinimumHeight(420)
        layout.addWidget(self._log_view, 1)

        layout.addSpacing(12)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        clear_btn = QPushButton("Очистить")
        clear_btn.setFixedWidth(104)
        _style_dialog_button(clear_btn, _dialog_btn_secondary())
        clear_btn.clicked.connect(self._clear_log)
        close_btn = QPushButton("Закрыть")
        close_btn.setFixedWidth(104)
        _style_dialog_button(close_btn, _dialog_btn_primary(COLORS["accent"]))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        dialog_w = int(avail.width() * 0.62) if avail else 860
        dialog_h = int(avail.height() * 0.82) if avail else 720
        min_w = min(720, dialog_w)
        min_h = min(560, dialog_h)
        _finalize_dialog_size(self, min_width=min_w, min_height=min_h)
        self.resize(dialog_w, dialog_h)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start(800)
        self._refresh_log()

    def _refresh_log(self) -> None:
        lines = self._app._log_lines
        text = "\n".join(lines)
        view = self._log_view
        if view.toPlainText() == text:
            return
        view.setPlainText(text)
        count = len(lines)
        self._count_label.setText(f"Строк в журнале: {count}")
        scrollbar = view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self) -> None:
        self._app._clear_log()
        self._refresh_log()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        self._timer.stop()
        super().reject()

    def accept(self) -> None:
        self._timer.stop()
        super().accept()


class AppBridge(QObject):
    """JavaScript bridge for the Paper Ops HTML UI."""

    def __init__(self, app: "GatewayApp") -> None:
        super().__init__()
        self._app = app

    @Slot()
    def requestState(self) -> None:
        self._app._push_ui_state()

    @Slot()
    def startGateway(self) -> None:
        self._app._start_gateway()

    @Slot()
    def stopGateway(self) -> None:
        self._app._stop_gateway()

    @Slot()
    def saveSettings(self) -> None:
        self._app._save_settings()

    @Slot()
    def clearLog(self) -> None:
        self._app._clear_log()

    @Slot()
    def openLog(self) -> None:
        self._app._open_log_journal()

    @Slot(str, int)
    def openBlock(self, kind: str, index: int) -> None:
        self._app._on_block_click(kind, index if index >= 0 else None)


class GatewayApp(QMainWindow):
    """Main desktop application — diagram-first main window."""

    def __init__(self) -> None:
        super().__init__()
        self.config_path = DEFAULT_CONFIG_PATH
        log_dir = self.config_path.parent / "logs"
        self._log_file_path = setup_logging("INFO", log_dir)
        logger.info("Файл журнала: %s", self._log_file_path)
        self.gateway_service = GatewayService()
        self.gateway_service.set_exit_callback(
            lambda unexpected: self._schedule_main(
                lambda u=unexpected: self._on_gateway_thread_exit(u)
            )
        )
        self.log_offset = 0
        self.unsaved = True
        self._closing = False
        self._ui_ready = False
        self._log_lines: list[str] = []

        self.payload: dict[str, Any] = {
            "remote_servers": [default_plc_server(i) for i in range(3)],
            "local_port": 4841,
            "namespace_uri": DEFAULT_LOCAL_SERVER["namespace_uri"],
            "folder_name": "GatewayData",
            "polling_interval": DEFAULT_POLLING_INTERVAL,
            "reconnect_interval": DEFAULT_RECONNECT_INTERVAL,
        }

        self.setWindowTitle(APP_NAME)
        _inherit_app_icon(self)
        self.setMinimumSize(1120, 820)
        self.resize(1120, 820)
        self._apply_style()
        self._build_ui()
        self._load_config()
        self._sync_start_button()

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._poll_logs)
        self._log_timer.start(800)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(1500)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"QMainWindow {{ background: {COLORS['bg']}; }}")

    def _set_status_badge(self, text: str, color: str) -> None:
        del text, color

    def _set_action_hint(self, text: str, kind: str = "muted") -> None:
        del text, kind

    def _build_ui(self) -> None:
        try:
            from PySide6.QtWebChannel import QWebChannel
            from PySide6.QtWebEngineCore import QWebEngineSettings
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            QMessageBox.critical(
                self,
                "WebEngine не установлен",
                "Для интерфейса нужен PySide6 с Qt WebEngine.\n\n"
                "Установите: pip install PySide6\n\n"
                f"Детали: {exc}",
            )
            raise

        class AppWebEngineView(QWebEngineView):
            """Main UI surface — no browser context menu on right-click."""

            def createStandardContextMenu(self):
                return None

            def contextMenuEvent(self, event) -> None:  # noqa: N802
                event.ignore()

        html_path = resource_path("paper_ops_app.html")
        if not html_path.exists():
            QMessageBox.critical(
                self,
                "Файл интерфейса не найден",
                f"Не найден paper_ops_app.html\n{html_path}",
            )
            raise FileNotFoundError(html_path)

        self.web_view = AppWebEngineView(self)
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        page = self.web_view.page()
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        page.setBackgroundColor(QColor(COLORS["bg"]))

        self.bridge = AppBridge(self)
        channel = QWebChannel(page)
        channel.registerObject("bridge", self.bridge)
        page.setWebChannel(channel)
        self.web_view.loadFinished.connect(self._on_ui_loaded)
        self.web_view.load(QUrl.fromLocalFile(str(html_path.resolve())))
        self.setCentralWidget(self.web_view)

    def _on_ui_loaded(self, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(
                self,
                "Интерфейс",
                f"Не удалось загрузить paper_ops_app.html\n{resource_path('paper_ops_app.html')}",
            )
            return
        self._ui_ready = True
        self._push_ui_state()

    def _build_ui_state(self) -> dict[str, Any]:
        block_status = self._build_diagram_status()
        servers = self.payload.get("remote_servers", [])
        hosts = [url_to_host_port(s.get("url", "")) for s in servers[:3]]
        while len(hosts) < 3:
            hosts.append("—")
        gw_addr = gateway_host_port(self.payload)

        busy_start = (
            self.gateway_service.running
            or self.gateway_service.stopping
            or self.unsaved
        )

        return {
            "buttons": {
                "start": not busy_start,
                "stop": self.gateway_service.running or self.gateway_service.stopping,
                "save": True,
            },
            "diagram": {
                "running": self.gateway_service.running,
                "plcs": [
                    {
                        "name": plc_display_name(servers[i] if i < len(servers) else None, i),
                        "addr": hosts[i],
                        "ok": block_status["plcs"][i],
                        "configured": block_status["plcs_configured"][i],
                    }
                    for i in range(3)
                ],
                "gateway": {
                    "ok": block_status["gateway_ok"],
                    "addr": gw_addr,
                },
                "customer": {"ok": block_status["customer_ok"]},
            },
        }

    def _push_ui_state(self) -> None:
        if not self._ui_ready:
            return
        state = self._build_ui_state()
        js = "window.applyAppState(" + json.dumps(state, ensure_ascii=False) + ");"
        self.web_view.page().runJavaScript(js)


    def _schedule_main(self, fn: Callable[[], None]) -> None:
        QTimer.singleShot(0, fn)

    def _on_block_click(self, kind: str, index: int | None) -> None:
        if kind != BLOCK_CUSTOMER:
            if self.gateway_service.stopping:
                QMessageBox.information(
                    self,
                    "Остановка шлюза",
                    "Подождите несколько секунд — шлюз ещё останавливается.\n"
                    "После этого можно открыть настройки блока.",
                )
                return
            if self.gateway_service.running:
                QMessageBox.information(
                    self,
                    "Шлюз работает",
                    "Сначала нажмите «Стоп» и дождитесь сообщения «Шлюз остановлен»,\n"
                    "затем откройте настройки ПЛК или шлюза.",
                )
                return
        if kind == BLOCK_PLC and index is not None:
            PlcSettingsDialog(
                self,
                index,
                self.payload["remote_servers"][index],
                on_apply=self._apply_plc_settings,
            ).exec()
        elif kind == BLOCK_GATEWAY:
            GatewaySettingsDialog(self, self.payload, on_apply=self._apply_gateway_settings).exec()
        elif kind == BLOCK_CUSTOMER:
            CustomerInfoDialog(self, self.payload).exec()

    def _apply_plc_settings(self, index: int, server: dict[str, Any]) -> None:
        servers = list(self.payload["remote_servers"])
        while len(servers) <= index:
            servers.append(default_plc_server(len(servers)))
        servers[index] = server
        self.payload["remote_servers"] = servers
        self._mark_unsaved()
        self._update_diagram()
        self._set_action_hint(f"ПЛК #{index + 1} обновлён (нажмите «Сохранить»)", "warning")

    def _apply_gateway_settings(self, changes: dict[str, Any]) -> None:
        self.payload.update(changes)
        self._mark_unsaved()
        self._update_diagram()
        self._set_action_hint("Параметры шлюза обновлены (нажмите «Сохранить»)", "warning")

    def _mark_unsaved(self) -> None:
        self.unsaved = True
        self._sync_start_button()

    def _mark_saved(self) -> None:
        self.unsaved = False
        self._sync_start_button()

    def _sync_start_button(self) -> None:
        self._push_ui_state()

    def _expand_log(self) -> None:
        self._open_log_journal()

    def _open_log_journal(self) -> None:
        LogJournalDialog(self).exec()

    def _require_saved_settings(self) -> bool:
        if not self.unsaved:
            return True
        QMessageBox.warning(
            self,
            "Сначала сохраните настройки",
            "Настройки не сохранены в settings.json.\n\n"
            "Нажмите «Сохранить», затем «Запустить шлюз».",
        )
        return False

    def _append_log(self, line: str) -> None:
        self._log_lines.append(line)
        if len(self._log_lines) > 1000:
            self._log_lines = self._log_lines[-1000:]

    def _clear_log(self) -> None:
        self.gateway_service.clear_logs()
        self._log_lines.clear()
        self.log_offset = 0

    def _load_config(self) -> None:
        config = load_config_or_default(self.config_path)
        loaded = config_to_payload(config)
        servers = loaded.get("remote_servers", [])
        while len(servers) < 3:
            servers.append(default_plc_server(len(servers)))
        loaded["remote_servers"] = servers[:3]
        self.payload.update(loaded)

        if self.config_path.exists():
            self._append_log(
                f"[GUI] Загружены настройки: {self.config_path.name} "
                f"(нажмите «Сохранить» перед запуском)"
            )
        else:
            self._append_log(
                f"[GUI] {self.config_path.name} не найден — значения по умолчанию "
                f"(сохраните перед запуском)"
            )

        self._update_diagram()

    def _read_payload(self) -> dict[str, Any]:
        return dict(self.payload)

    def _update_diagram(self) -> None:
        self._push_ui_state()

    def _build_diagram_status(self) -> dict[str, Any]:
        gw_status = self.gateway_service.get_status()
        if self.gateway_service.running:
            gw_status = {**gw_status, "running": True}
        servers = self.payload.get("remote_servers", [])[:3]
        polling = float(self.payload.get("polling_interval", DEFAULT_POLLING_INTERVAL))
        return evaluate_diagram_status(gw_status, servers, polling)

    def _save_settings(self) -> None:
        try:
            config = payload_to_config(self._read_payload())
            save_config(config, self.config_path)
            self._mark_saved()
            self._set_action_hint(f"Сохранено в {self.config_path.name}", "success")
            self._append_log(f"[GUI] Сохранено: {self.config_path}")
        except (ValueError, OSError) as exc:
            self._set_action_hint(str(exc), "danger")
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))

    def _start_gateway(self, *, skip_save_check: bool = False) -> None:
        if not skip_save_check and not self._require_saved_settings():
            return

        try:
            config = payload_to_config(self._read_payload())
        except ValueError as exc:
            QMessageBox.critical(self, "Ошибка конфигурации", str(exc))
            return

        self._set_status_badge("Запуск…", "#93C5FD")
        self._set_action_hint("Запуск шлюза…", "accent")
        self._push_ui_state()

        try:
            self.gateway_service.start(config)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Шлюз", str(exc))
            self._sync_start_button()
            self._update_status_label()
            raise
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка запуска", str(exc))
            self._sync_start_button()
            self._update_status_label()
            raise

    def _stop_gateway(self) -> None:
        if not self.gateway_service.running and not self.gateway_service.stopping:
            return
        self._set_status_badge("Остановка…", COLORS["text_muted"])
        self._set_action_hint("Остановка шлюза…", "muted")
        self._push_ui_state()
        self.gateway_service.stop(done_callback=lambda: self._schedule_main(self._on_gateway_stopped))

    def _on_gateway_stopped(self) -> None:
        self._set_status_badge("Готов", "#86EFAC")
        self._set_action_hint("Шлюз остановлен — можно настраивать блоки", "success")
        self._sync_start_button()
        self._update_diagram()

    def _on_gateway_thread_exit(self, unexpected: bool) -> None:
        """Handle gateway thread exit; auto-restart on unexpected stop."""
        if unexpected and not self._closing:
            self._set_status_badge("Сбой", "#FCA5A5")
            self._set_action_hint("Шлюз неожиданно остановился", "danger")
            self._update_diagram()
            if self.unsaved:
                self._append_log(
                    "[GUI] Автоперезапуск отменён: сохраните настройки и запустите вручную"
                )
                return
            self._append_log(
                f"[GUI] Автоперезапуск шлюза через {AUTO_RESTART_DELAY_MS // 1000} с…"
            )
            QTimer.singleShot(AUTO_RESTART_DELAY_MS, self._auto_restart_gateway)
            return
        if not unexpected:
            self._sync_start_button()
            self._update_diagram()

    def _auto_restart_gateway(self) -> None:
        if self._closing:
            return
        if self.gateway_service.running or self.gateway_service.stopping:
            return
        if self.unsaved:
            self._append_log("[GUI] Автоперезапуск отменён: настройки не сохранены")
            return
        self._append_log("[GUI] Автоперезапуск шлюза…")
        try:
            self._start_gateway(skip_save_check=True)
        except Exception as exc:
            self._append_log(f"[GUI] Автоперезапуск не удался: {exc}")
            QTimer.singleShot(AUTO_RESTART_RETRY_MS, self._auto_restart_gateway)

    def _poll_logs(self) -> None:
        lines, total = self.gateway_service.logs_since(self.log_offset)
        if lines:
            self._log_lines.extend(lines)
            if len(self._log_lines) > 1000:
                self._log_lines = self._log_lines[-1000:]
            self.log_offset = total

    def _poll_status(self) -> None:
        gw_status = self.gateway_service.get_status()

        if self.gateway_service.stopping:
            self._set_status_badge("Остановка…", COLORS["text_muted"])
        elif self.gateway_service.running:
            block_status = self._build_diagram_status()
            if block_status["gateway_ok"]:
                bad_plcs = sum(
                    1
                    for i, configured in enumerate(block_status["plcs_configured"])
                    if configured and not block_status["plcs"][i]
                )
                if bad_plcs:
                    self._set_status_badge("Работает", "#86EFAC")
                    self._set_action_hint(
                        f"Шлюз работает · без данных: {bad_plcs} ПЛК",
                        "warning",
                    )
                else:
                    self._set_status_badge("Работает", "#86EFAC")
                    self._set_action_hint("Шлюз работает · все ПЛК отдают данные", "success")
            elif gw_status.get("local_server_ok"):
                self._set_status_badge("Запуск…", "#93C5FD")
            else:
                self._set_status_badge("Запуск…", "#93C5FD")
        else:
            self._set_status_badge("Готов", "#86EFAC")

        self._push_ui_state()

    def _update_status_label(self) -> None:
        if self.gateway_service.stopping:
            self._set_status_badge("Остановка…", COLORS["text_muted"])
        elif self.gateway_service.running:
            self._set_status_badge("Запуск…", "#93C5FD")
        else:
            self._set_status_badge("Готов", "#86EFAC")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._closing:
            event.accept()
            return

        if self.gateway_service.running or self.gateway_service.stopping:
            reply = QMessageBox.question(
                self,
                "Выход",
                "Шлюз работает. Остановить и выйти?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self._closing = True
            event.ignore()
            self._set_status_badge("Остановка…", COLORS["text_muted"])
            self.gateway_service.stop(done_callback=lambda: self._schedule_main(self.close))
            return

        event.accept()

    def bring_to_front(self) -> None:
        """Show and activate the main window (used for single-instance handoff)."""
        self.showNormal()
        self.raise_()
        self.activateWindow()


SINGLE_INSTANCE_KEY = "OPC_UA_Gateway_Gui"


def _notify_running_instance() -> bool:
    """Return True if another instance accepted the handoff request."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if not socket.waitForConnected(500):
        socket.abort()
        return False

    socket.write(b"raise")
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def _setup_single_instance_server(window: GatewayApp) -> QLocalServer:
    server = QLocalServer(window)
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    if not server.listen(SINGLE_INSTANCE_KEY):
        raise RuntimeError(f"Не удалось создать локальный сервер: {server.errorString()}")

    def on_new_connection() -> None:
        socket = server.nextPendingConnection()
        if socket is None:
            return
        socket.waitForReadyRead(1000)
        socket.readAll()
        socket.disconnectFromServer()
        window.bring_to_front()

    server.newConnection.connect(on_new_connection)
    return server


def main() -> None:
    if sys.version_info < (3, 11):
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Требуется Python",
            f"Нужен Python 3.11 или новее (сейчас: "
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})",
        )
        sys.exit(1)

    try:
        _set_windows_app_id()
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setStyleSheet(_app_stylesheet())
        _configure_application(app)

        if _notify_running_instance():
            QMessageBox.information(
                None,
                "OPC UA Gateway",
                "Программа уже запущена.",
            )
            sys.exit(0)

        window = GatewayApp()
        _setup_single_instance_server(window)
        window.show()
        sys.exit(app.exec())
    except Exception as exc:
        logging.exception("Ошибка запуска GUI")
        if QApplication.instance() is None:
            app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Ошибка запуска",
            f"Не удалось запустить программу:\n\n{exc}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
