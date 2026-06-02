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


class ThreeDGSMCPSessionError(ThreeDGSMCPClientError):
    pass


MCP_PROTOCOL_VERSION = "2025-06-18"
_MCP_SESSION_ID: str | None = None


def _headers(session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if THREEDGS_MCP_API_KEY:
        headers["Authorization"] = f"Bearer {THREEDGS_MCP_API_KEY}"
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


def _is_session_error_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "mcp-session-id" in lowered
        or "mcp session" in lowered
        or "session not found" in lowered
        or "session is not initialized" in lowered
        or "session expired" in lowered
    )


def _raise_rpc_error(error: Any) -> None:
    if not isinstance(error, dict):
        raise ThreeDGSMCPClientError(f"3DGS MCP RPC error: {json.dumps(error, ensure_ascii=False)}")

    message = str(error.get("message") or "")
    if _is_session_error_message(message):
        raise ThreeDGSMCPSessionError(f"3DGS MCP RPC session error: {json.dumps(error, ensure_ascii=False)}")
    raise ThreeDGSMCPClientError(f"3DGS MCP RPC error: {json.dumps(error, ensure_ascii=False)}")


def _post_json(
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    expect_body: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not THREEDGS_MCP_SERVER_URL:
        raise ThreeDGSMCPClientError("THREEDGS_MCP_SERVER_URL is not configured.")

    request = urllib.request.Request(
        THREEDGS_MCP_SERVER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(session_id),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=MCP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"3DGS MCP HTTP {exc.code}: {detail}"
        if exc.code in {400, 404} and _is_session_error_message(detail):
            raise ThreeDGSMCPSessionError(message) from exc
        raise ThreeDGSMCPClientError(message) from exc
    except Exception as exc:
        raise ThreeDGSMCPClientError(f"3DGS MCP request failed: {exc}") from exc

    if not expect_body:
        return {}, headers

    data = _decode_json_response(body)
    error = data.get("error")
    if error:
        _raise_rpc_error(error)
    return data, headers


def _rpc(method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": method,
        "params": params or {},
    }
    data, _headers_ = _post_json(payload, session_id=session_id)
    return data


def _notify(method: str, params: dict[str, Any] | None = None, *, session_id: str) -> None:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    }
    _post_json(payload, session_id=session_id, expect_body=False)


def _initialize() -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agent-material-backend", "version": "0.2.0"},
        },
    }
    data, headers = _post_json(payload)
    result = data.get("result")
    if not isinstance(result, dict) or result.get("protocolVersion") != MCP_PROTOCOL_VERSION:
        raise ThreeDGSMCPClientError("3DGS MCP initialize returned an unsupported protocol version.")

    session_id = headers.get("mcp-session-id")
    if not session_id:
        raise ThreeDGSMCPClientError("3DGS MCP initialize did not return Mcp-Session-Id.")

    try:
        _notify("notifications/initialized", session_id=session_id)
    except Exception:
        # Notification failure is non-fatal; the server has the session
        # and will reject subsequent calls until initialized. The next RPC
        # will trigger re-initialization anyway.
        pass
    _MCP_SESSION_ID = session_id
    return session_id


def _ensure_session() -> str:
    global _MCP_SESSION_ID
    if not _MCP_SESSION_ID:
        _MCP_SESSION_ID = _initialize()
    return _MCP_SESSION_ID


def _clear_session() -> None:
    global _MCP_SESSION_ID
    _MCP_SESSION_ID = None


def _extract_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("isError") is True:
        content = result.get("content")
        message = "3DGS MCP tool returned an error."
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    message = item["text"]
                    break
        raise ThreeDGSMCPClientError(message)

    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("render_url"):
            return structured

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

    params = {
        "name": "3dgs.create_render",
        "arguments": arguments,
    }

    try:
        data = _rpc("tools/call", params, session_id=_ensure_session())
    except ThreeDGSMCPSessionError:
        _clear_session()
        data = _rpc("tools/call", params, session_id=_ensure_session())

    result = _extract_result(data.get("result"))
    result.setdefault("ok", True)
    result.setdefault("source", "3dgs:mcp")
    result.setdefault("ttl_sec", ttl_sec or THREEDGS_RENDER_TTL_SEC)
    return result
