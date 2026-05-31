from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from config.settings import (
    MCP_TIMEOUT_SEC,
    THREEDGS_MCP_API_KEY,
    THREEDGS_MCP_SERVER_URL,
    THREEDGS_RENDER_TTL_SEC,
)


class ThreeDGSMCPClientError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if THREEDGS_MCP_API_KEY:
        headers["visualization-api-key"] = THREEDGS_MCP_API_KEY
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

    raise ThreeDGSMCPClientError("3DGS MCP response was not valid JSON.")


def _rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not THREEDGS_MCP_SERVER_URL:
        raise ThreeDGSMCPClientError("THREEDGS_MCP_SERVER_URL is not configured.")

    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": method,
        "params": params or {},
    }
    request = urllib.request.Request(
        THREEDGS_MCP_SERVER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=MCP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ThreeDGSMCPClientError(f"3DGS MCP HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ThreeDGSMCPClientError(f"3DGS MCP request failed: {exc}") from exc

    data = _decode_json_response(body)
    error = data.get("error")
    if error:
        raise ThreeDGSMCPClientError(f"3DGS MCP RPC error: {json.dumps(error, ensure_ascii=False)}")
    return data


def _extract_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("render_url"):
        return result

    if isinstance(result, dict):
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
                if isinstance(payload, dict) and payload.get("render_url"):
                    return payload

    raise ThreeDGSMCPClientError("3DGS MCP response did not contain a render result.")


def create_render(
    filename: str,
    *,
    quality: str = "auto",
    ttl_sec: int | None = None,
) -> dict[str, Any]:
    if not filename.strip():
        raise ThreeDGSMCPClientError("filename is required.")

    arguments: dict[str, Any] = {
        "filename": filename.strip(),
        "quality": (quality or "auto").strip() or "auto",
    }
    if ttl_sec is not None:
        arguments["ttl_sec"] = int(ttl_sec)

    data = _rpc(
        "tools/call",
        {
            "name": "3dgs.create_render",
            "arguments": arguments,
        },
    )
    result = _extract_result(data.get("result"))
    result.setdefault("ok", True)
    result.setdefault("source", "3dgs:mcp")
    result.setdefault("ttl_sec", ttl_sec or THREEDGS_RENDER_TTL_SEC)
    return result
