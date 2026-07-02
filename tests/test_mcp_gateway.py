from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core import mcp_gateway


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


def _server() -> dict[str, object]:
    return {
        "url": "https://example.test/mcp",
        "headers": {"visualization-api-key": "test-key"},
    }


def test_call_tool_decodes_plain_json_and_extracts_render_url() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": "1", "result": {"render_url": "https://view.test/a"}})

    with (
        patch.object(mcp_gateway, "get_server", return_value=_server()),
        patch.object(mcp_gateway.urllib.request, "urlopen", return_value=FakeResponse(body)) as urlopen,
    ):
        data = mcp_gateway.call_tool("dos-mcp-server", "dos.dos_file", {"filename": "dos.txt"})

    assert data["result"]["render_url"] == "https://view.test/a"
    assert mcp_gateway.extract_render_url(data) == "https://view.test/a"
    request = urlopen.call_args.args[0]
    assert request.headers["Visualization-api-key"] == "test-key"
    assert json.loads(request.data.decode("utf-8"))["params"]["name"] == "dos.dos_file"


def test_call_tool_decodes_sse_json() -> None:
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"render_url":"https://view.test/sse"}}\n\n'

    with (
        patch.object(mcp_gateway, "get_server", return_value=_server()),
        patch.object(mcp_gateway.urllib.request, "urlopen", return_value=FakeResponse(body)),
    ):
        data = mcp_gateway.call_tool("dos-mcp-server", "dos.dos_file", {})

    assert mcp_gateway.extract_render_url(data["result"]) == "https://view.test/sse"


def test_extract_render_url_prefers_structured_content() -> None:
    result = {
        "render_url": "https://view.test/direct",
        "structuredContent": {"render_url": "https://view.test/structured"},
    }

    assert mcp_gateway.extract_render_url(result) == "https://view.test/direct"


def test_extract_render_url_from_structured_content_without_direct_url() -> None:
    result = {"structuredContent": {"render_url": "https://view.test/structured"}}

    assert mcp_gateway.extract_render_url(result) == "https://view.test/structured"


def test_extract_render_url_from_content_text_json() -> None:
    result = {
        "content": [
            {
                "type": "text",
                "text": '{"render_url":"https://view.test/from-text"}',
            }
        ]
    }

    assert mcp_gateway.extract_render_url(result) == "https://view.test/from-text"


def test_call_tool_raises_on_rpc_error() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": "1", "error": {"code": -32602, "message": "bad args"}})

    with (
        patch.object(mcp_gateway, "get_server", return_value=_server()),
        patch.object(mcp_gateway.urllib.request, "urlopen", return_value=FakeResponse(body)),
    ):
        with pytest.raises(mcp_gateway.MCPRPCError, match="bad args"):
            mcp_gateway.call_tool("dos-mcp-server", "dos.dos_file", {})


def test_call_tool_raises_on_result_tool_error() -> None:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "render failed"}],
            },
        }
    )

    with (
        patch.object(mcp_gateway, "get_server", return_value=_server()),
        patch.object(mcp_gateway.urllib.request, "urlopen", return_value=FakeResponse(body)),
    ):
        with pytest.raises(mcp_gateway.MCPToolError, match="render failed"):
            mcp_gateway.call_tool("dos-mcp-server", "dos.dos_file", {})


def test_extract_render_url_raises_when_missing() -> None:
    with pytest.raises(mcp_gateway.MCPRenderUrlMissingError, match="render_url"):
        mcp_gateway.extract_render_url({"content": [{"type": "text", "text": "no url"}]})
