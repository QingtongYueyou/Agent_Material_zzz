from __future__ import annotations

import json
import re
import secrets
import time
from html import escape
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import CORS_ALLOWED_ORIGINS, THREEDGS_MCP_API_KEY
from services.three_dgs_mcp import rendering


app = FastAPI(title="Agent Material 3DGS MCP", version="0.1.0")
create_render = rendering.create_render

VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
VIEWER_DIST_DIR = VIEWER_DIR / "dist"
VIEWER_INDEX_HTML = VIEWER_DIST_DIR / "index.html"
VIEWER_ASSETS_DIR = VIEWER_DIST_DIR / "assets"
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SESSION_TTL_SEC = 3600
_MCP_SESSIONS: dict[str, dict[str, Any]] = {}
_MCP_SESSION_LOCK = Lock()
_LOCAL_MCP_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8090",
    "http://localhost:8090",
}

app.mount(
    "/viewer/assets",
    StaticFiles(directory=VIEWER_ASSETS_DIR, check_dir=False),
    name="viewer-assets",
)

_ROOT_PATTERN = re.compile(
    r'<(?P<tag>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*)\bid=(?P<quote>["\'])root(?P=quote)(?P<after>[^>]*)>'
    r".*?</(?P=tag)>",
    flags=re.IGNORECASE | re.DOTALL,
)


def _json_rpc_success(request_id: Any, result: Any, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result}, headers=headers)


def _json_rpc_error(request_id: Any, code: int, message: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        status_code=status_code,
    )


def _http_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def _notification_accepted() -> Response:
    return Response(status_code=202)


def _tool_spec() -> dict[str, Any]:
    return {
        "name": "3dgs.create_render",
        "title": "Create 3DGS Render",
        "description": "Create a temporary 3DGS viewer session for a resolved splat asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "quality": {
                    "type": "string",
                    "enum": ["auto", "preview", "balanced", "full", "source"],
                    "default": rendering.DEFAULT_QUALITY,
                },
                "render_profile": {
                    "type": "string",
                    "enum": ["performance", "quality"],
                    "default": rendering.DEFAULT_RENDER_PROFILE,
                },
                "ttl_sec": {"type": "integer", "minimum": 1},
            },
            "required": ["filename"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "source": {"type": "string"},
                "session_id": {"type": "string"},
                "render_url": {"type": "string"},
                "expires_at": {"type": "number"},
                "asset": {"type": "object"},
            },
            "required": ["ok", "source", "session_id", "render_url", "expires_at", "asset"],
        },
    }


def _is_authorized(request: Request) -> bool:
    if not THREEDGS_MCP_API_KEY:
        return True
    authorization = request.headers.get("authorization", "")
    if authorization == f"Bearer {THREEDGS_MCP_API_KEY}":
        return True
    return request.headers.get("visualization-api-key") == THREEDGS_MCP_API_KEY


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin in set(CORS_ALLOWED_ORIGINS).union(_LOCAL_MCP_ORIGINS)


def _prune_mcp_sessions() -> None:
    current = time.time()
    expired = [
        session_id
        for session_id, session in _MCP_SESSIONS.items()
        if float(session.get("expires_at", 0)) <= current
    ]
    for session_id in expired:
        _MCP_SESSIONS.pop(session_id, None)


def _create_mcp_session(protocol_version: str) -> str:
    session_id = secrets.token_urlsafe(32)
    with _MCP_SESSION_LOCK:
        _prune_mcp_sessions()
        _MCP_SESSIONS[session_id] = {
            "protocol_version": protocol_version,
            "initialized": False,
            "created_at": time.time(),
            "expires_at": time.time() + MCP_SESSION_TTL_SEC,
        }
    return session_id


def _get_mcp_session(request: Request) -> tuple[str, dict[str, Any]] | JSONResponse:
    session_id = request.headers.get("mcp-session-id", "")
    if not session_id:
        return _http_error(400, "Mcp-Session-Id header is required.")
    with _MCP_SESSION_LOCK:
        _prune_mcp_sessions()
        session = _MCP_SESSIONS.get(session_id)
        if session is None:
            return _http_error(404, "MCP session not found.")
    return session_id, session


def _validate_protocol_header(request: Request) -> JSONResponse | None:
    return None


def _tool_result(result: dict[str, Any], *, is_error: bool = False, text: str | None = None) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": text if text is not None else json.dumps(result, ensure_ascii=False),
            }
        ],
        "structuredContent": result,
        "isError": is_error,
    }


@app.get("/mcp")
def mcp_get() -> Response:
    return Response(status_code=405)


@app.post("/mcp", response_model=None)
async def mcp_endpoint(request: Request):
    if not _origin_allowed(request):
        return _http_error(403, "Origin is not allowed for 3DGS MCP requests.")
    if not _is_authorized(request):
        return _http_error(401, "Unauthorized 3DGS MCP request.")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return _http_error(415, "Content-Type must be application/json.")

    accept = request.headers.get("accept", "*/*")
    if "application/json" not in accept and "text/event-stream" not in accept and "*/*" not in accept:
        return _http_error(406, "Accept must allow application/json or text/event-stream.")

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return _json_rpc_error(None, -32700, "Invalid JSON-RPC payload.")

    if not isinstance(payload, dict):
        return _json_rpc_error(None, -32600, "JSON-RPC payload must be an object.")

    if payload.get("jsonrpc") != "2.0":
        return _json_rpc_error(payload.get("id"), -32600, "JSON-RPC version must be 2.0.")

    if "method" not in payload:
        return _notification_accepted()

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    is_notification = "id" not in payload

    if method == "initialize":
        client_protocol = str(params.get("protocolVersion") or MCP_PROTOCOL_VERSION)
        mcp_session_id = _create_mcp_session(client_protocol)
        return _json_rpc_success(
            request_id,
            {
                "protocolVersion": client_protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "agent-material-3dgs",
                    "title": "Agent Material 3DGS Renderer",
                    "version": "0.1.0",
                },
            },
            headers={"Mcp-Session-Id": mcp_session_id},
        )

    protocol_error = _validate_protocol_header(request)
    if protocol_error is not None:
        return protocol_error

    session_lookup = _get_mcp_session(request)
    if isinstance(session_lookup, JSONResponse):
        return session_lookup
    mcp_session_id, mcp_session = session_lookup

    if method == "notifications/initialized":
        with _MCP_SESSION_LOCK:
            if mcp_session_id in _MCP_SESSIONS:
                _MCP_SESSIONS[mcp_session_id]["initialized"] = True
        return _notification_accepted()

    if method == "ping":
        return _notification_accepted() if is_notification else _json_rpc_success(request_id, {})

    if not bool(mcp_session.get("initialized")):
        return _json_rpc_error(request_id, -32002, "MCP session is not initialized.")

    if method == "tools/list":
        return _notification_accepted() if is_notification else _json_rpc_success(request_id, {"tools": [_tool_spec()]})

    if method != "tools/call":
        return _json_rpc_error(request_id, -32601, f"Unsupported method: {method}")

    if is_notification:
        return _notification_accepted()

    if params.get("name") != "3dgs.create_render":
        return _json_rpc_error(request_id, -32602, "Unsupported tool name.")

    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        return _json_rpc_error(request_id, -32602, "Tool arguments must be an object.")

    try:
        result = rendering.create_render(
            str(arguments.get("filename") or ""),
            quality=str(arguments.get("quality") or rendering.DEFAULT_QUALITY),
            render_profile=str(arguments.get("render_profile") or rendering.DEFAULT_RENDER_PROFILE),
            ttl_sec=arguments.get("ttl_sec"),
        )
    except rendering.RenderCreateError as exc:
        return _json_rpc_success(request_id, _tool_result({"ok": False, "error": str(exc)}, is_error=True, text=str(exc)))
    except (TypeError, ValueError) as exc:
        return _json_rpc_error(request_id, -32602, str(exc))

    return _json_rpc_success(request_id, _tool_result(result))


@app.get("/health")
def health() -> dict[str, Any]:
    rendering.prune_expired_sessions()
    return {
        "ok": True,
        "service": "agent-material-3dgs-mcp",
        "sessions": len(rendering.sessions),
        "public_base_url": rendering._public_base_url(),
        "auth_required": bool(THREEDGS_MCP_API_KEY),
        "session_file": str(rendering.THREEDGS_SESSION_FILE),
    }


def _session_config_script(session_id: str, token: str) -> str:
    config_url = f"/viewer/sessions/{quote(session_id, safe='')}/config?token={quote(token, safe='')}"
    payload = json.dumps(config_url).replace("</", "<\\/")
    return f'<script type="application/json" id="session-config-url">{payload}</script>'


def _viewer_token_cookie_name(session_id: str) -> str:
    return f"3dgs_viewer_token_{session_id}"


def _viewer_token_from_request(request: Request, session_id: str, token: str) -> str:
    return token or request.cookies.get(_viewer_token_cookie_name(session_id), "")


def _set_viewer_token_cookie(response: Response, session_id: str, token: str) -> None:
    response.set_cookie(
        key=_viewer_token_cookie_name(session_id),
        value=token,
        path=f"/viewer/sessions/{quote(session_id, safe='')}",
        httponly=True,
        samesite="lax",
    )


def _viewer_unbuilt_html(session_id: str, token: str, message: str) -> str:
    safe_session_id = escape(session_id, quote=True)
    safe_message = escape(message, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>3DGS Viewer Not Built</title>
  <style>
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101418;
      color: #f4f7fb;
    }}
    #root {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      box-sizing: border-box;
    }}
    .viewer-build-error {{
      max-width: 720px;
      border: 1px solid #39424e;
      border-radius: 8px;
      padding: 20px;
      background: #18202a;
      line-height: 1.5;
    }}
    code {{
      color: #9bd3ff;
    }}
  </style>
</head>
<body>
  <main id="root" data-session-id="{safe_session_id}">
    <section class="viewer-build-error">
      <h1>3DGS viewer app is not built</h1>
      <p>{safe_message}</p>
      <p>Build the standalone viewer before serving sessions: <code>cd services/three_dgs_mcp/viewer && npm install && npm run build</code>.</p>
    </section>
  </main>
  {_session_config_script(session_id, token)}
</body>
</html>"""


def _rewrite_viewer_index(index_html: str, session_id: str, token: str) -> str:
    safe_session_id = escape(session_id, quote=True)
    html = re.sub(
        r'(?P<prefix>\b(?:src|href)=["\'])(?:/)?assets/',
        r"\g<prefix>/viewer/assets/",
        index_html,
    )

    root = f'<main id="root" data-session-id="{safe_session_id}"></main>'
    html, root_count = _ROOT_PATTERN.subn(root, html, count=1)
    if root_count == 0:
        html = re.sub(r"<body([^>]*)>", rf"<body\1>\n  {root}", html, count=1, flags=re.IGNORECASE)

    config_script = _session_config_script(session_id, token)
    if 'id="session-config-url"' not in html and "id='session-config-url'" not in html:
        html = html.replace(root, f"{root}\n  {config_script}", 1)
    return html


def _assert_viewer_session(session_id: str, token: str) -> None:
    try:
        rendering.get_session_config(session_id, token)
    except rendering.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except rendering.SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except rendering.SessionTokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/viewer/sessions/{session_id}", response_class=HTMLResponse)
def viewer_session(response: Response, session_id: str, token: str = Query(default="")) -> str:
    _assert_viewer_session(session_id, token)
    _set_viewer_token_cookie(response, session_id, token)
    if not VIEWER_INDEX_HTML.exists():
        return _viewer_unbuilt_html(
            session_id,
            token,
            f"Expected Vite build output at {VIEWER_INDEX_HTML}, but index.html was not found.",
        )

    try:
        index_html = VIEWER_INDEX_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        return _viewer_unbuilt_html(session_id, token, f"Could not read {VIEWER_INDEX_HTML}: {exc}")

    if "/assets/" not in index_html and 'src="assets/' not in index_html and "href=\"assets/" not in index_html:
        return _viewer_unbuilt_html(
            session_id,
            token,
            f"{VIEWER_INDEX_HTML} does not reference Vite asset bundles. Rebuild the viewer app.",
        )

    return _rewrite_viewer_index(index_html, session_id, token)



@app.get("/viewer/sessions/{session_id}/config")
def viewer_session_config(request: Request, session_id: str, token: str = Query(default="")) -> dict[str, Any]:
    try:
        return rendering.get_session_config(session_id, _viewer_token_from_request(request, session_id, token))
    except rendering.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except rendering.SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except rendering.SessionTokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/viewer/sessions/{session_id}/assets/{relative_path:path}")
def session_asset_file(
    request: Request,
    session_id: str,
    relative_path: str,
    token: str = Query(default=""),
) -> FileResponse:
    try:
        return FileResponse(
            rendering.resolve_session_asset_path(
                session_id,
                relative_path,
                _viewer_token_from_request(request, session_id, token),
            )
        )
    except rendering.AssetPathError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except rendering.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except rendering.SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except rendering.SessionTokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
