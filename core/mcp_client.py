from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from config.settings import (
    MCP_API_KEY,
    MCP_RENDER_TTL_SEC,
    MCP_SERVER_URL,
    MCP_TIMEOUT_SEC,
)


class MCPClientError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if MCP_API_KEY:
        headers["visualization-api-key"] = MCP_API_KEY
    return headers


def _decode_json_response(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        return data

    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    raise MCPClientError("MCP 返回内容不是有效 JSON。")


def _rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not MCP_SERVER_URL:
        raise MCPClientError("MCP_SERVER_URL 未配置。")
    if not MCP_API_KEY:
        raise MCPClientError("MCP_API_KEY 未配置。")

    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": method,
        "params": params or {},
    }
    request = urllib.request.Request(
        MCP_SERVER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=MCP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MCPClientError(f"MCP HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise MCPClientError(f"MCP 请求失败: {exc}") from exc

    data = _decode_json_response(body)
    error = data.get("error")
    if error:
        raise MCPClientError(f"MCP RPC 错误: {json.dumps(error, ensure_ascii=False)}")
    return data


def _extract_render_url(result: Any) -> str:
    if isinstance(result, dict):
        direct_url = result.get("render_url")
        if isinstance(direct_url, str) and direct_url.strip():
            return direct_url.strip()

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
                    render_url = payload.get("render_url")
                    if isinstance(render_url, str) and render_url.strip():
                        return render_url.strip()

    raise MCPClientError("MCP 响应中没有 render_url。")


def initialize() -> dict[str, Any]:
    return _rpc(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agent-material-streamlit", "version": "0.1.0"},
        },
    )


def list_tools() -> dict[str, Any]:
    return _rpc("tools/list")


def process_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise MCPClientError(f"MCP 文件不存在: {path}")

    content_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
    data = _rpc(
        "tools/call",
        {
            "name": "fz.process_file",
            "arguments": {
                "filename": path.name,
                "content_base64": content_base64,
            },
        },
    )
    render_url = _extract_render_url(data.get("result"))
    created_at = time.time()
    return {
        "ok": True,
        "render_url": render_url,
        "created_at": created_at,
        "expires_at": created_at + MCP_RENDER_TTL_SEC,
        "ttl_sec": MCP_RENDER_TTL_SEC,
        "source": "mcp:file",
        "filename": path.name,
    }


def process_http(http_url: str) -> dict[str, Any]:
    if not http_url.strip():
        raise MCPClientError("http_url 不能为空。")

    data = _rpc(
        "tools/call",
        {
            "name": "fz.process_http",
            "arguments": {"http_url": http_url.strip()},
        },
    )
    render_url = _extract_render_url(data.get("result"))
    created_at = time.time()
    return {
        "ok": True,
        "render_url": render_url,
        "created_at": created_at,
        "expires_at": created_at + MCP_RENDER_TTL_SEC,
        "ttl_sec": MCP_RENDER_TTL_SEC,
        "source": "mcp:http",
        "http_url": http_url.strip(),
    }


def is_render_url_fresh(expires_at: float | int | None, *, skew_sec: int = 30) -> bool:
    if expires_at is None:
        return False
    try:
        return time.time() < float(expires_at) - skew_sec
    except (TypeError, ValueError):
        return False
