from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import mcp_registry


def _write_config(path: Path, server_name: str, url: str = "https://example.test/mcp") -> None:
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    server_name: {
                        "url": url,
                        "headers": {"visualization-api-key": "test-key"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_load_registry_reads_docs_server_json() -> None:
    registry = mcp_registry.load_registry()

    assert "dos-mcp-server" in registry
    assert registry["dos-mcp-server"]["url"].startswith("http://")
    assert registry["dos-mcp-server"]["headers"]["visualization-api-key"]


def test_load_registry_rejects_duplicate_server_names(tmp_path) -> None:
    _write_config(tmp_path / "a.json", "same-server")
    _write_config(tmp_path / "b.json", "same-server")

    with pytest.raises(mcp_registry.MCPRegistryError, match="Duplicate MCP server"):
        mcp_registry.load_registry(tmp_path)


def test_load_registry_rejects_non_http_url(tmp_path) -> None:
    _write_config(tmp_path / "bad.json", "bad-server", url="file:///tmp/server")

    with pytest.raises(mcp_registry.MCPRegistryError, match="absolute http"):
        mcp_registry.load_registry(tmp_path)


def test_get_server_uses_configured_directory(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / "one.json", "one-server", url="https://example.test/one")
    monkeypatch.setattr(mcp_registry, "MCP_CONFIG_DIR", tmp_path)

    server = mcp_registry.get_server("one-server")

    assert server["url"] == "https://example.test/one"
