from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config.settings import MCP_CONFIG_DIR


class MCPRegistryError(RuntimeError):
    pass


def _validate_server_config(
    server_name: str,
    raw_config: Any,
    *,
    source_file: Path,
) -> dict[str, Any]:
    if not isinstance(server_name, str) or not server_name.strip():
        raise MCPRegistryError(f"Invalid empty MCP server name in {source_file}.")
    if not isinstance(raw_config, dict):
        raise MCPRegistryError(f"MCP server {server_name!r} in {source_file} must be an object.")

    url = raw_config.get("url")
    if not isinstance(url, str) or not url.strip():
        raise MCPRegistryError(f"MCP server {server_name!r} is missing url.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MCPRegistryError(f"MCP server {server_name!r} url must be absolute http(s).")

    headers = raw_config.get("headers", {})
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise MCPRegistryError(f"MCP server {server_name!r} headers must be an object.")
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise MCPRegistryError(
                f"MCP server {server_name!r} headers must be string-to-string."
            )

    return {
        "name": server_name.strip(),
        "url": url.strip(),
        "headers": dict(headers),
        "source_file": str(source_file),
    }


def load_registry(config_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    directory = Path(config_dir or MCP_CONFIG_DIR).expanduser()
    if not directory.exists() or not directory.is_dir():
        raise MCPRegistryError(f"MCP config directory does not exist: {directory}")

    registry: dict[str, dict[str, Any]] = {}
    for config_path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPRegistryError(f"Invalid MCP config JSON: {config_path}") from exc

        if not isinstance(payload, dict):
            raise MCPRegistryError(f"MCP config must be an object: {config_path}")
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict):
            raise MCPRegistryError(f"MCP config missing mcpServers object: {config_path}")

        for server_name, raw_config in servers.items():
            validated = _validate_server_config(
                server_name,
                raw_config,
                source_file=config_path,
            )
            name = validated["name"]
            if name in registry:
                first_source = registry[name].get("source_file")
                raise MCPRegistryError(
                    f"Duplicate MCP server {name!r} in {config_path}; already defined in {first_source}."
                )
            registry[name] = validated

    return registry


def get_server(server_name: str) -> dict[str, Any]:
    if not isinstance(server_name, str) or not server_name.strip():
        raise MCPRegistryError("server_name is required.")

    registry = load_registry()
    name = server_name.strip()
    try:
        return registry[name]
    except KeyError as exc:
        raise MCPRegistryError(f"MCP server {name!r} is not configured.") from exc
