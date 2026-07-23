"""Load, save, and build gateway configuration (JSON)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def app_dir() -> Path:
    """Application directory: next to .exe (PyInstaller) or source files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DEFAULT_CONFIG_PATH = app_dir() / "settings.json"

DEFAULT_LOCAL_SERVER: dict[str, Any] = {
    "url": "opc.tcp://0.0.0.0:4841",
    "namespace_uri": "http://127.0.0.1/opcua/gateway/",
    "folder_name": "GatewayData",
    "variables": [],
}

DEFAULT_POLLING_INTERVAL = 2.0
DEFAULT_RECONNECT_INTERVAL = 5.0

DEFAULT_REMOTE_SERVERS: list[dict[str, Any]] = [
    {
        "name": "BHK1_PLC1",
        "url": "opc.tcp://192.168.1.10:4840",
        "nodes": [
            {"node_id": "ns=2;i=1001", "local_node_id": "BHK1_PLC1_Temperature"},
            {"node_id": "ns=2;i=1002", "local_node_id": "BHK1_PLC1_Pressure"},
        ],
    },
    {
        "name": "BHK1_PLC2",
        "url": "opc.tcp://192.168.1.11:4840",
        "nodes": [
            {"node_id": "ns=2;i=1001", "local_node_id": "BHK1_PLC2_Temperature"},
            {"node_id": "ns=2;i=1002", "local_node_id": "BHK1_PLC2_Pressure"},
        ],
    },
    {
        "name": "BHK1_PLC3",
        "url": "opc.tcp://192.168.1.12:4840",
        "nodes": [
            {"node_id": "ns=2;i=1001", "local_node_id": "BHK1_PLC3_Temperature"},
            {"node_id": "ns=2;i=1002", "local_node_id": "BHK1_PLC3_Pressure"},
        ],
    },
]


def default_config() -> dict[str, Any]:
    """Default gateway configuration (3 OWEN210 PLCs, port 4841)."""
    local_server = dict(DEFAULT_LOCAL_SERVER)
    local_server["variables"] = auto_create_local_variables(DEFAULT_REMOTE_SERVERS)
    return build_config_dict(
        remote_servers=json.loads(json.dumps(DEFAULT_REMOTE_SERVERS)),
        local_server=local_server,
        polling_interval=DEFAULT_POLLING_INTERVAL,
        reconnect_interval=DEFAULT_RECONNECT_INTERVAL,
    )


def load_config_or_default(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from disk or return built-in defaults."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return default_config()
    return load_config(path)


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from a JSON file."""
    path = config_path or DEFAULT_CONFIG_PATH
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def save_config(config: dict[str, Any], config_path: Path | None = None) -> None:
    """Save configuration to a JSON file."""
    path = config_path or DEFAULT_CONFIG_PATH
    with path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, ensure_ascii=False, indent=2)
        config_file.write("\n")


def auto_create_local_variables(
    remote_servers: list[dict[str, Any]],
    default_data_type: str = "Double",
    default_initial_value: float = 0.0,
) -> list[dict[str, Any]]:
    """Build local_server.variables from remote_servers.nodes mappings."""
    variables: list[dict[str, Any]] = []
    seen: set[str] = set()

    for remote_config in remote_servers:
        for node_config in remote_config.get("nodes", []):
            local_node_id = node_config.get("local_node_id", "").strip()
            if not local_node_id or local_node_id in seen:
                continue
            seen.add(local_node_id)
            variables.append(
                {
                    "node_id": local_node_id,
                    "name": local_node_id.replace("_", " "),
                    "initial_value": default_initial_value,
                    "data_type": default_data_type,
                }
            )

    return variables


def build_config_dict(
    remote_servers: list[dict[str, Any]],
    local_server: dict[str, Any],
    polling_interval: float = DEFAULT_POLLING_INTERVAL,
    reconnect_interval: float = DEFAULT_RECONNECT_INTERVAL,
    *,
    auto_variables: bool = False,
) -> dict[str, Any]:
    """Assemble a configuration dictionary for OpcUaGateway."""
    local_server_config = dict(local_server)
    if auto_variables:
        local_server_config["variables"] = auto_create_local_variables(remote_servers)
    elif "variables" not in local_server_config:
        local_server_config["variables"] = []

    return {
        "remote_servers": remote_servers,
        "local_server": local_server_config,
        "polling_interval": polling_interval,
        "reconnect_interval": reconnect_interval,
    }


def local_server_url_from_port(port: int | str) -> str:
    """Build opc.tcp endpoint URL from a local port number."""
    return f"opc.tcp://0.0.0.0:{int(port)}"


def parse_local_port(url: str, default: int = 4841) -> int:
    """Extract port from opc.tcp URL or return default."""
    if not url:
        return default
    try:
        return int(url.rsplit(":", 1)[-1])
    except (IndexError, ValueError):
        return default
