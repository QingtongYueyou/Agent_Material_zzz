from __future__ import annotations

import pytest

from core import mcp_router
from core.mcp_registry import load_registry


def test_resolve_route_for_dos_file() -> None:
    route = mcp_router.resolve_route(
        "dos",
        "file",
        {"file_id": "file_20260701_0123456789abcdef", "extension": ".txt"},
    )

    assert route["server_name"] == "dos-mcp-server"
    assert route["tool_name"] == "dos.dos_file"
    assert route["file_id"] == "file_20260701_0123456789abcdef"
    assert route["title"] == "DOS 可视化"


def test_resolve_route_extracts_extension_from_filename() -> None:
    route = mcp_router.resolve_route(
        "binary_phase",
        "file",
        {"file_id": "file_20260701_0123456789abcdef", "filename": "phase.xlsx"},
    )

    assert route["server_name"] == "hot2-mcp-server"
    assert route["tool_name"] == "hot2.binary_xlsx_file"


def test_resolve_route_rejects_unsupported_intent() -> None:
    with pytest.raises(mcp_router.MCPRouteError, match="Unsupported MCP intent"):
        mcp_router.resolve_route(
            "missing_intent",
            "file",
            {"file_id": "file_20260701_0123456789abcdef", "extension": ".zip"},
        )


def test_resolve_route_for_band_zip_file() -> None:
    route = mcp_router.resolve_route(
        "band",
        "file",
        {"file_id": "file_20260701_0123456789abcdef", "extension": ".zip"},
    )

    assert route["server_name"] == "nb-mcp-server"
    assert route["tool_name"] == "nb.band_zip_file"


def test_route_table_covers_configured_mcp_servers() -> None:
    configured = set(load_registry())
    routed = {route["server_name"] for route in mcp_router.ROUTE_TABLE.values()}

    assert configured <= routed


def test_resolve_route_rejects_non_file_input() -> None:
    with pytest.raises(mcp_router.MCPRouteError, match="Only input_type='file'"):
        mcp_router.resolve_route(
            "dos",
            "url",
            {"file_id": "file_20260701_0123456789abcdef", "extension": ".txt"},
        )


def test_resolve_route_rejects_extension_mismatch() -> None:
    with pytest.raises(mcp_router.MCPRouteError, match="does not accept extension"):
        mcp_router.resolve_route(
            "structure",
            "file",
            {"file_id": "file_20260701_0123456789abcdef", "extension": ".txt"},
        )


def test_resolve_route_requires_file_id() -> None:
    with pytest.raises(mcp_router.MCPRouteError, match="metadata.file_id"):
        mcp_router.resolve_route("xrd", "file", {"extension": ".dat"})
