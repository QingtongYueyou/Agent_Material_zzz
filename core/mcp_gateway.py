from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from config.settings import MCP_TIMEOUT_SEC
from core.mcp_registry import MCPRegistryError, get_server


class MCPGatewayError(RuntimeError):
    pass


class MCPRPCError(MCPGatewayError):
    pass


class MCPToolError(MCPGatewayError):
    pass


class MCPRenderUrlMissingError(MCPGatewayError):
    pass


def _decode_json_response(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        return data

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    raise MCPGatewayError("MCP response was not valid JSON or SSE JSON.")


def _headers(server_headers: dict[str, str]) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    headers.update(server_headers)
    return headers


def _format_error_payload(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return json.dumps(error, ensure_ascii=False)


def _tool_error_message(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                return item["text"].strip()
    return "MCP tool returned an error."


def call_tool(server_name: str, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise MCPGatewayError("tool_name is required.")
    if arguments is not None and not isinstance(arguments, dict):
        raise MCPGatewayError("arguments must be a dict.")

    try:
        server = get_server(server_name)
    except MCPRegistryError:
        raise

    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "tools/call",
        "params": {
            "name": tool_name.strip(),
            "arguments": arguments or {},
        },
    }
    request = urllib.request.Request(
        server["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(server.get("headers", {})),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=MCP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MCPGatewayError(f"MCP HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise MCPGatewayError(f"MCP request failed: {exc}") from exc

    data = _decode_json_response(body)
    error = data.get("error")
    if error:
        raise MCPRPCError(f"MCP RPC error: {_format_error_payload(error)}")

    result = data.get("result")
    if isinstance(result, dict) and result.get("isError") is True:
        raise MCPToolError(_tool_error_message(result))

    return data


def _url_from_mapping(payload: dict[str, Any]) -> str | None:
    render_url = payload.get("render_url")
    if isinstance(render_url, str) and render_url.strip():
        return render_url.strip()

    structured = payload.get("structuredContent")
    if isinstance(structured, dict):
        render_url = structured.get("render_url")
        if isinstance(render_url, str) and render_url.strip():
            return render_url.strip()

    return None


def extract_render_url(result: Any) -> str:
    if isinstance(result, dict) and "result" in result and not _url_from_mapping(result):
        result = result.get("result")

    if isinstance(result, dict) and result.get("isError") is True:
        raise MCPToolError(_tool_error_message(result))

    if isinstance(result, dict):
        render_url = _url_from_mapping(result)
        if render_url:
            return render_url

        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    render_url = _url_from_mapping(payload)
                    if render_url:
                        return render_url

    raise MCPRenderUrlMissingError("MCP response did not contain render_url.")
