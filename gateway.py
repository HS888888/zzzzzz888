"""OPC UA gateway: read from PLCs and publish on a local OPC UA server."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from asyncua import Client, Server, ua

logger = logging.getLogger(__name__)

DATA_TYPE_MAP: dict[str, ua.VariantType] = {
    "Boolean": ua.VariantType.Boolean,
    "SByte": ua.VariantType.SByte,
    "Byte": ua.VariantType.Byte,
    "Int16": ua.VariantType.Int16,
    "UInt16": ua.VariantType.UInt16,
    "Int32": ua.VariantType.Int32,
    "UInt32": ua.VariantType.UInt32,
    "Int64": ua.VariantType.Int64,
    "UInt64": ua.VariantType.UInt64,
    "Float": ua.VariantType.Float,
    "Double": ua.VariantType.Double,
    "String": ua.VariantType.String,
    "DateTime": ua.VariantType.DateTime,
}


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "gateway.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def setup_logging(level: str = "INFO", log_dir: Path | str | None = None) -> Path:
    """Configure console and rotating file logging. Returns the log file path."""
    base_dir = Path(__file__).resolve().parent
    target_dir = Path(log_dir) if log_dir is not None else base_dir / LOG_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / LOG_FILE_NAME

    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    # A windowed exe has no console. Writing to stderr there can attach
    # a black terminal or fail when sys.stderr is None.
    if sys.stderr is not None and not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return log_path


def get_variant_type(type_name: str) -> ua.VariantType:
    """Resolve VariantType from a configuration string."""
    try:
        return DATA_TYPE_MAP[type_name]
    except KeyError as exc:
        supported = ", ".join(sorted(DATA_TYPE_MAP))
        raise ValueError(
            f"Unknown data type '{type_name}'. Supported: {supported}"
        ) from exc


INTEGER_VARIANT_TYPES = frozenset(
    {
        ua.VariantType.SByte,
        ua.VariantType.Byte,
        ua.VariantType.Int16,
        ua.VariantType.UInt16,
        ua.VariantType.Int32,
        ua.VariantType.UInt32,
        ua.VariantType.Int64,
        ua.VariantType.UInt64,
    }
)

FLOAT_VARIANT_TYPES = frozenset({ua.VariantType.Float, ua.VariantType.Double})


def coerce_value(value: Any, variant_type: ua.VariantType) -> Any:
    """Convert a remote PLC value to the local gateway variable type."""
    if variant_type == ua.VariantType.Boolean:
        return bool(value)
    if variant_type in INTEGER_VARIANT_TYPES:
        return int(value)
    if variant_type in FLOAT_VARIANT_TYPES:
        return float(value)
    if variant_type == ua.VariantType.String:
        return str(value)
    return value


def build_node_id(node_id: str | dict[str, Any]) -> str:
    """
    Build a NodeId string.

    Supports:
    - full string: "ns=2;i=1001" or "ns=2;s=Temperature"
    - object: {"ns": 2, "i": 1001} or {"ns": 2, "s": "Temperature"}
    """
    if isinstance(node_id, str):
        return node_id

    namespace = node_id["ns"]
    if "i" in node_id:
        return f"ns={namespace};i={node_id['i']}"
    if "s" in node_id:
        return f"ns={namespace};s={node_id['s']}"
    if "g" in node_id:
        return f"ns={namespace};g={node_id['g']}"
    if "b" in node_id:
        return f"ns={namespace};b={node_id['b']}"

    raise ValueError(f"Invalid NodeId: {node_id}")


class OpcUaGateway:
    """OPC UA gateway: remote PLC client and local server for downstream clients."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.server = Server()
        self.namespace_index: int | None = None
        self.local_variables: dict[str, Any] = {}
        self.local_variable_types: dict[str, ua.VariantType] = {}
        self._remote_tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._status_lock = threading.Lock()
        self._status: dict[str, Any] = {
            "running": False,
            "gateway_ok": False,
            "local_server_ok": False,
            "error": None,
            "plcs": {},
        }

    def get_status(self) -> dict[str, Any]:
        """Thread-safe snapshot of gateway and PLC connection state."""
        with self._status_lock:
            return {
                "running": self._status["running"],
                "gateway_ok": self._status["gateway_ok"],
                "local_server_ok": self._status["local_server_ok"],
                "error": self._status["error"],
                "plcs": {
                    url: dict(entry)
                    for url, entry in self._status["plcs"].items()
                },
            }

    def _set_plc_status(
        self, url: str, *, connected: bool, read_ok: bool = False
    ) -> None:
        with self._status_lock:
            entry = self._status["plcs"].setdefault(
                url, {"connected": False, "last_read": None}
            )
            entry["connected"] = connected
            if read_ok:
                entry["last_read"] = time.monotonic()
            elif not connected:
                entry["last_read"] = None

    def _reset_status(self) -> None:
        with self._status_lock:
            self._status.update(
                running=False,
                gateway_ok=False,
                local_server_ok=False,
                error=None,
            )
            for entry in self._status["plcs"].values():
                entry["connected"] = False
                entry["last_read"] = None

    async def init_local_server(self) -> None:
        """Initialize the local OPC UA server and variables."""
        local_config = self.config["local_server"]
        endpoint = local_config["url"]
        namespace_uri = local_config["namespace_uri"]
        folder_name = local_config.get("folder_name", "GatewayData")

        await self.server.init()
        self.server.set_endpoint(endpoint)
        self.server.set_server_name("MS SERVICE")

        self.namespace_index = await self.server.register_namespace(namespace_uri)
        idx = self.namespace_index

        gateway_folder = await self.server.nodes.objects.add_object(idx, folder_name)

        for variable_config in local_config["variables"]:
            node_id = variable_config["node_id"]
            browse_name = variable_config.get("name", node_id)
            initial_value = variable_config["initial_value"]
            data_type_name = variable_config["data_type"]
            variant_type = get_variant_type(data_type_name)

            variable_node = await gateway_folder.add_variable(
                ua.NodeId(node_id, idx),
                ua.QualifiedName(browse_name, idx),
                initial_value,
                varianttype=variant_type,
            )
            await variable_node.set_writable(False)

            self.local_variables[node_id] = variable_node
            self.local_variable_types[node_id] = variant_type
            logger.info(
                "Создана локальная переменная %s (%s, %s)",
                node_id,
                browse_name,
                data_type_name,
            )

        logger.info("Локальный OPC UA сервер инициализирован: %s", endpoint)
        with self._status_lock:
            self._status["local_server_ok"] = True

    async def _update_local_variable(self, local_node_id: str, value: Any) -> None:
        """Write a value to a local gateway variable."""
        variable_node = self.local_variables.get(local_node_id)
        if variable_node is None:
            logger.error("Локальная переменная «%s» не найдена в конфигурации", local_node_id)
            return

        variant_type = self.local_variable_types.get(local_node_id)
        if variant_type is None:
            logger.error(
                "Тип локальной переменной «%s» не найден в конфигурации",
                local_node_id,
            )
            return

        coerced = coerce_value(value, variant_type)
        await variable_node.write_value(coerced)
        logger.debug("Обновлено %s = %r", local_node_id, coerced)

    async def _read_remote_server_loop(self, remote_config: dict[str, Any]) -> None:
        """Poll one remote OPC UA server (PLC)."""
        url = remote_config["url"]
        name = remote_config.get("name", url)
        nodes = remote_config["nodes"]
        polling_interval = float(self.config.get("polling_interval", 2.0))
        reconnect_interval = float(self.config.get("reconnect_interval", 5.0))

        while not self._stop_event.is_set():
            client = Client(url=url)
            try:
                logger.info("Подключение к удалённому серверу %s (%s)", name, url)
                async with client:
                    logger.info("Подключено к %s", name)
                    self._set_plc_status(url, connected=True)

                    while not self._stop_event.is_set():
                        for node_config in nodes:
                            remote_node_id = build_node_id(node_config["node_id"])
                            local_node_id = node_config["local_node_id"]

                            try:
                                node = client.get_node(remote_node_id)
                                value = await node.read_value()
                                self._set_plc_status(url, connected=True, read_ok=True)
                                await self._update_local_variable(local_node_id, value)
                            except Exception as exc:
                                logger.error(
                                    "Ошибка чтения %s с %s: %s",
                                    remote_node_id,
                                    name,
                                    exc,
                                )

                        try:
                            await asyncio.wait_for(
                                self._stop_event.wait(),
                                timeout=polling_interval,
                            )
                            break
                        except asyncio.TimeoutError:
                            continue

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._set_plc_status(url, connected=False)
                logger.error(
                    "Соединение с %s (%s) потеряно: %s. Повтор через %.1f с",
                    name,
                    url,
                    exc,
                    reconnect_interval,
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=reconnect_interval,
                    )
                    break
                except asyncio.TimeoutError:
                    continue

        logger.info("Опрос удалённого сервера %s остановлен", name)

    async def read_remote_servers(self) -> None:
        """Start background polling tasks for all remote servers."""
        for remote_config in self.config.get("remote_servers", []):
            url = remote_config["url"]
            with self._status_lock:
                self._status["plcs"][url] = {"connected": False, "last_read": None}
            task = asyncio.create_task(
                self._read_remote_server_loop(remote_config),
                name=f"poll-{remote_config.get('name', remote_config['url'])}",
            )
            self._remote_tasks.append(task)

        logger.info("Запущено задач опроса: %d", len(self._remote_tasks))

    async def start(self) -> None:
        """Start the gateway: local server and PLC polling."""
        with self._status_lock:
            self._status["running"] = True
            self._status["gateway_ok"] = True
            self._status["error"] = None

        try:
            await self.init_local_server()
            logger.info("Запуск локального OPC UA сервера...")
            async with self.server:
                await self.read_remote_servers()
                logger.info("Шлюз работает")
                await self._stop_event.wait()
        except Exception as exc:
            with self._status_lock:
                self._status["gateway_ok"] = False
                self._status["local_server_ok"] = False
                self._status["error"] = str(exc)
            raise

    async def stop(self) -> None:
        """Stop the gateway gracefully."""
        logger.info("Остановка шлюза...")
        self._stop_event.set()

        for task in self._remote_tasks:
            task.cancel()

        if self._remote_tasks:
            await asyncio.gather(*self._remote_tasks, return_exceptions=True)

        self._reset_status()
        logger.info("Шлюз остановлен")
